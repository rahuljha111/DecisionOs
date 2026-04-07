"""
DecisionOS — FastAPI Backend
Single entry point for Cloud Run deployment.

Endpoints:
  GET  /health              — liveness probe
  GET  /stream_decision     — SSE decision pipeline (legacy)
  POST /chat                — SSE decision pipeline (primary)
  GET  /auth/google         — begin Google OAuth2 flow
  GET  /auth/google/callback— OAuth2 callback, stores token
"""

import os
import json
import uvicorn
from datetime import datetime

from fastapi import FastAPI, Depends, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session

from ai_engine.orchestrator import stream_decision
from backend.db.database import get_db, init_db, UserToken

from fastapi.staticfiles import StaticFiles


# ─────────────────────────────────────────────
# APP INIT
# ─────────────────────────────────────────────

app = FastAPI(title="DecisionOS", version="1.0.0")
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],     # tighten to your frontend domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create tables on startup (idempotent)
@app.on_event("startup")
def on_startup():
    init_db()
    print("[DecisionOS] Database tables ready.")


# ─────────────────────────────────────────────
# HEALTH CHECK (Cloud Run requires this)
# ─────────────────────────────────────────────

@app.get("/health")
def health_check():
    return {"status": "alive", "timestamp": datetime.utcnow().isoformat()}


# ─────────────────────────────────────────────
# DECISION ENDPOINTS
# ─────────────────────────────────────────────

@app.get("/stream_decision")
async def stream_decision_get(
    message: str = Query(..., description="User's decision request"),
    user_id: str = Query("anonymous", description="User identifier"),
    db: Session = Depends(get_db)
):
    """SSE endpoint — GET variant for EventSource compatibility."""
    return StreamingResponse(
        stream_decision(db, user_id, message),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # disable nginx buffering on Cloud Run
        }
    )


@app.post("/chat")
async def chat(
    request: Request,
    db: Session = Depends(get_db)
):
    """SSE endpoint — POST variant accepting JSON body."""
    body = await request.json()
    message = body.get("message", "")
    user_id = body.get("user_id", "anonymous")

    if not message:
        return JSONResponse({"error": "message is required"}, status_code=400)

    return StreamingResponse(
        stream_decision(db, user_id, message),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


# ─────────────────────────────────────────────
# GOOGLE OAUTH2 (Calendar access)
# ─────────────────────────────────────────────

GOOGLE_CLIENT_ID     = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI  = os.environ.get(
    "GOOGLE_REDIRECT_URI",
    "http://localhost:8080/auth/google/callback"
)

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]


@app.get("/auth/google")
def auth_google(user_id: str = Query(...)):
    """
    Redirect user to Google's OAuth2 consent page.
    Pass user_id as state so the callback can associate the token.
    """
    try:
        from google_auth_oauthlib.flow import Flow
    except ImportError:
        return JSONResponse(
            {"error": "google-auth-oauthlib not installed"},
            status_code=500
        )

    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uris": [GOOGLE_REDIRECT_URI],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=SCOPES,
        redirect_uri=GOOGLE_REDIRECT_URI,
    )

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        state=user_id,
        prompt="consent",
    )
    return RedirectResponse(auth_url)


@app.get("/auth/google/callback")
def auth_google_callback(
    code: str = Query(...),
    state: str = Query(...),   # state = user_id
    db: Session = Depends(get_db)
):
    """Exchange auth code for tokens and persist them."""
    try:
        from google_auth_oauthlib.flow import Flow
    except ImportError:
        return JSONResponse(
            {"error": "google-auth-oauthlib not installed"},
            status_code=500
        )

    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uris": [GOOGLE_REDIRECT_URI],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=SCOPES,
        redirect_uri=GOOGLE_REDIRECT_URI,
    )

    flow.fetch_token(code=code)
    creds = flow.credentials

    token_data = {
        "token":         creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri":     creds.token_uri,
        "client_id":     creds.client_id,
        "client_secret": creds.client_secret,
        "scopes":        list(creds.scopes or []),
    }

    # Upsert token for this user
    user_id = state
    existing = db.query(UserToken).filter(UserToken.user_id == user_id).first()
    if existing:
        existing.token_json = json.dumps(token_data)
        existing.updated_at = datetime.utcnow()
    else:
        db.add(UserToken(user_id=user_id, token_json=json.dumps(token_data)))
    db.commit()

    # Redirect back to frontend after auth
    frontend_url = os.environ.get("FRONTEND_URL", "/")
    return RedirectResponse(f"{frontend_url}?auth=success&user_id={user_id}")


# ─────────────────────────────────────────────
# ENTRYPOINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, reload=False)