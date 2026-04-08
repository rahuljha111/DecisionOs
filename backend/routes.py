"""
API Routes for DecisionOS.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse, RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError
from typing import List, Optional
from collections import Counter
from datetime import datetime, timedelta
import os
import json
import subprocess
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError
from pydantic import BaseModel, Field
from openai import AsyncOpenAI
import google.auth
from google.auth.transport.requests import Request as GoogleAuthRequest

from backend.db.database import get_db, Decision, CalendarEvent, Task, get_or_create_user, User, GoogleCalendarToken
from backend.schemas import DecisionRequest, EventCreate, TaskCreate, ExecuteActionRequest
from ai_engine.orchestrator import stream_decision
from ai_engine.utils.helpers import safe_json
from backend.tools.google_calendar import (
    get_google_calendar_service,
    is_google_calendar_available,
    CREDENTIALS_FILE
)

router = APIRouter()

gemini_client = AsyncOpenAI(
        api_key=os.environ.get("GEMINI_API_KEY", ""),
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
)

GEMINI_MODEL = "gemini-2.0-flash"
VERTEX_MODEL = os.environ.get("VERTEX_AI_MODEL", "google/gemini-2.5-flash")
VERTEX_LOCATION = os.environ.get("VERTEX_AI_LOCATION", "us-central1")
VERTEX_PROJECT = os.environ.get("VERTEX_AI_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT")
PRIORITIZE_TEMPERATURE = 0.2

PRIORITIZE_TASKS_SYSTEM_PROMPT = """You are a task prioritization planner.

Return JSON only in this exact format:
{
    "prioritized_tasks": ["task 1", "task 2"],
    "decision": "Do <task> first, then <task>.",
    "reason": "Short explanation based on urgency, deadlines, and impact."
}

Rules:
1. Use all input tasks exactly once in prioritized_tasks.
2. Keep task text exactly as input text.
3. Order tasks from highest to lowest priority.
4. decision must explicitly mention first and second tasks when possible.
5. reason must be concise and concrete.
6. Do not add markdown or any text outside JSON.
7. Avoid generic statements. Mention concrete constraints like time windows, deadlines, and calendar conflicts if provided.
"""


class PrioritizeRequest(BaseModel):
    """Request schema for day prioritization."""
    user_id: str
    tasks: List[str] = Field(default_factory=list)
    meetings: List[dict] = Field(default_factory=list)


class TaskPrioritizeRequest(BaseModel):
    """Request schema for simple task prioritization demos."""
    user_id: str = "system"
    tasks: List[str] = Field(default_factory=list)


def _parse_datetime(value):
    """Parse datetime from ISO strings while accepting datetime values directly."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return None
    return None


def _normalize_prioritized_tasks(input_tasks: List[str], model_tasks: List[str]) -> List[str]:
    """Keep model order while ensuring the list contains each input task exactly once."""
    normalized_input = [task.strip() for task in input_tasks if isinstance(task, str) and task.strip()]
    normalized_model = [str(task).strip() for task in model_tasks if str(task).strip()]

    input_counts = Counter(task.lower() for task in normalized_input)
    remaining_counts = input_counts.copy()

    input_by_key = {}
    for task in normalized_input:
        input_by_key.setdefault(task.lower(), []).append(task)

    use_index = Counter()
    ordered: List[str] = []

    for task in normalized_model:
        key = task.lower()
        if remaining_counts.get(key, 0) <= 0:
            continue
        original_task = input_by_key[key][use_index[key]]
        ordered.append(original_task)
        use_index[key] += 1
        remaining_counts[key] -= 1

    for task in normalized_input:
        key = task.lower()
        if remaining_counts.get(key, 0) <= 0:
            continue
        ordered.append(task)
        remaining_counts[key] -= 1

    return ordered


def _resolve_vertex_project() -> Optional[str]:
    """Resolve Vertex project from env, ADC, metadata, or gcloud config."""
    project = os.environ.get("VERTEX_AI_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT") or VERTEX_PROJECT
    if project:
        return project

    try:
        _, inferred_project = google.auth.default()
        if inferred_project:
            return inferred_project
    except Exception:
        pass

    # Cloud Run metadata server fallback
    try:
        meta_req = urllib_request.Request(
            url="http://metadata.google.internal/computeMetadata/v1/project/project-id",
            headers={"Metadata-Flavor": "Google"},
            method="GET",
        )
        with urllib_request.urlopen(meta_req, timeout=2) as resp:
            meta_project = resp.read().decode("utf-8").strip()
            if meta_project:
                return meta_project
    except Exception:
        pass

    # Local developer fallback
    try:
        output = subprocess.check_output(
            ["gcloud", "config", "get-value", "project"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2,
        ).strip()
        if output and output != "(unset)":
            return output
    except Exception:
        pass

    return None


def _resolve_vertex_bearer_token() -> str:
    """Resolve a bearer token for Vertex requests (ADC first, gcloud fallback)."""
    try:
        credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        credentials.refresh(GoogleAuthRequest())
        if credentials.token:
            return credentials.token
    except Exception:
        pass

    # Local developer fallback: use logged-in gcloud user token.
    gcloud_candidates = [
        "gcloud",
        "gcloud.cmd",
        r"C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd",
        r"C:\Program Files\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd",
    ]
    for gcloud_bin in gcloud_candidates:
        try:
            token = subprocess.check_output(
                [gcloud_bin, "auth", "print-access-token"],
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=10,
            ).strip()
            if token:
                return token
        except Exception:
            continue

    raise HTTPException(
        status_code=503,
        detail="Vertex AI authentication failed. Configure ADC or login with gcloud auth login."
    )


def _get_upcoming_calendar_context(db: Session, user_id: str, horizon_hours: int = 24) -> List[dict]:
    """Return upcoming events for model context using Google/MCP first, DB fallback."""
    now = datetime.now()
    horizon = now + timedelta(hours=horizon_hours)

    # Primary path: MCP tools (Google Calendar when authenticated, DB fallback internally).
    try:
        from backend.tools.mcp_tools import MCPTools

        mcp = MCPTools(db, user_id)
        events, _source = mcp.get_events_in_range(now, horizon)
        if events:
            normalized = []
            for event in events[:10]:
                start_val = event.get("start_time")
                end_val = event.get("end_time")

                if isinstance(start_val, datetime):
                    start_iso = start_val.isoformat()
                else:
                    start_iso = str(start_val or "")

                if isinstance(end_val, datetime):
                    end_iso = end_val.isoformat()
                else:
                    end_iso = str(end_val or "")

                normalized.append(
                    {
                        "title": event.get("title") or "Calendar event",
                        "start": start_iso,
                        "end": end_iso,
                    }
                )
            if normalized:
                return normalized
    except Exception:
        pass

    # Explicit DB fallback if MCP path yields no events.
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        return []

    events = (
        db.query(CalendarEvent)
        .filter(
            CalendarEvent.user_id == user.id,
            CalendarEvent.status != "cancelled",
            CalendarEvent.end_time >= now,
            CalendarEvent.start_time <= horizon,
        )
        .order_by(CalendarEvent.start_time.asc())
        .limit(10)
        .all()
    )

    return [
        {
            "title": event.title,
            "start": event.start_time.isoformat(),
            "end": event.end_time.isoformat(),
        }
        for event in events
    ]


async def _prioritize_tasks_with_gemini(tasks: List[str]) -> dict:
    """Use Gemini to prioritize tasks and return normalized API output."""
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(status_code=503, detail="GEMINI_API_KEY is not configured")

    try:
        completion = await gemini_client.chat.completions.create(
            model=GEMINI_MODEL,
            temperature=PRIORITIZE_TEMPERATURE,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": PRIORITIZE_TASKS_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps({"tasks": tasks})},
            ],
        )
    except Exception as exc:
        message = str(exc)
        if "429" in message or "RESOURCE_EXHAUSTED" in message or "quota" in message.lower():
            raise HTTPException(
                status_code=503,
                detail="Gemini quota exceeded. Please retry later or update API billing/quota settings."
            ) from exc
        raise HTTPException(status_code=502, detail="Gemini request failed") from exc

    raw = (completion.choices[0].message.content or "") if completion.choices else ""
    parsed = safe_json(raw)
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=502, detail="Gemini returned invalid JSON")

    model_prioritized = parsed.get("prioritized_tasks", [])
    if not isinstance(model_prioritized, list):
        raise HTTPException(status_code=502, detail="Gemini response missing prioritized_tasks list")

    prioritized_tasks = _normalize_prioritized_tasks(tasks, model_prioritized)
    if not prioritized_tasks:
        raise HTTPException(status_code=502, detail="Gemini response produced empty prioritized task list")

    decision = (parsed.get("decision") or "").strip()
    reason = (parsed.get("reason") or "").strip()

    if not decision:
        if len(prioritized_tasks) > 1:
            decision = f"Do {prioritized_tasks[0]} first, then {prioritized_tasks[1]}."
        else:
            decision = f"Do {prioritized_tasks[0]} first."

    if not reason:
        reason = "This order balances urgency, deadlines, and overall impact."

    return {
        "prioritized_tasks": prioritized_tasks,
        "decision": decision,
        "reason": reason,
    }


def _build_prioritize_response(tasks: List[str], parsed: dict) -> dict:
    """Normalize model JSON into stable API response shape."""
    model_prioritized = parsed.get("prioritized_tasks", [])
    if not isinstance(model_prioritized, list):
        raise HTTPException(status_code=502, detail="Model response missing prioritized_tasks list")

    prioritized_tasks = _normalize_prioritized_tasks(tasks, model_prioritized)
    if not prioritized_tasks:
        raise HTTPException(status_code=502, detail="Model response produced empty prioritized task list")

    decision = (parsed.get("decision") or "").strip()
    reason = (parsed.get("reason") or "").strip()

    if not decision:
        if len(prioritized_tasks) > 1:
            decision = f"Do {prioritized_tasks[0]} first, then {prioritized_tasks[1]}."
        else:
            decision = f"Do {prioritized_tasks[0]} first."

    if not reason:
        reason = "This order balances urgency, deadlines, and overall impact."

    return {
        "prioritized_tasks": prioritized_tasks,
        "decision": decision,
        "reason": reason,
    }


async def _prioritize_tasks_with_vertex(tasks: List[str], calendar_events: List[dict]) -> dict:
    """Use Vertex AI Gemini (ADC auth) for task prioritization."""
    import logging
    logger = logging.getLogger(__name__)
    
    project = _resolve_vertex_project()
    location = os.environ.get("VERTEX_AI_LOCATION") or VERTEX_LOCATION
    model = os.environ.get("VERTEX_AI_MODEL") or VERTEX_MODEL

    if not project:
        raise HTTPException(status_code=503, detail="Vertex AI project is not configured. Set VERTEX_AI_PROJECT or gcloud default project.")

    token = _resolve_vertex_bearer_token()
    
    logger.info(f"Vertex Prioritize: project={project}, location={location}, model={model}, tasks={len(tasks)}, calendar_events={len(calendar_events)}")

    url = (
        f"https://{location}-aiplatform.googleapis.com/v1/"
        f"projects/{project}/locations/{location}/endpoints/openapi/chat/completions"
    )

    payload = {
        "model": model,
        "response_format": {"type": "json_object"},
        "temperature": PRIORITIZE_TEMPERATURE,
        "messages": [
            {"role": "system", "content": PRIORITIZE_TASKS_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps({
                    "tasks": tasks,
                    "calendar_events": calendar_events,
                    "instruction": "Prioritize tasks while considering calendar conflicts and fixed-time meetings."
                }),
            },
        ],
    }

    req = urllib_request.Request(
        url=url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib_request.urlopen(req, timeout=45) as resp:
            response_body = resp.read().decode("utf-8")
            vertex_response = json.loads(response_body)
            logger.info(f"Vertex response received: {vertex_response}")
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="ignore") if hasattr(exc, "read") else ""
        message = error_body or str(exc)
        logger.error(f"Vertex HTTPError {exc.code}: {message}")
        if exc.code in (429, 503):
            raise HTTPException(status_code=503, detail="Vertex AI quota exceeded. Please retry later.") from exc
        if exc.code in (401, 403):
            raise HTTPException(status_code=503, detail="Vertex AI permission denied. Ensure Cloud Run service account has roles/aiplatform.user.") from exc
        if exc.code == 404:
            raise HTTPException(status_code=503, detail="Vertex model not accessible. Set VERTEX_AI_MODEL to an allowed model (for example google/gemini-2.5-flash).") from exc
        raise HTTPException(status_code=502, detail=f"Vertex AI request failed ({exc.code})") from exc
    except URLError as exc:
        raise HTTPException(status_code=502, detail="Vertex AI network request failed") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Vertex AI response parsing failed: {exc}") from exc

    choices = vertex_response.get("choices", [])
    text = ""
    if choices and isinstance(choices[0], dict):
        message = choices[0].get("message") or {}
        if isinstance(message, dict):
            text = message.get("content", "")

    parsed = safe_json(text)
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=502, detail="Vertex AI returned invalid JSON")

    return _build_prioritize_response(tasks, parsed)


@router.post("/decide")
async def make_decision(
    request: DecisionRequest,
    db: Session = Depends(get_db)
):
    """
    Main decision endpoint with SSE streaming.
    
    Streams real-time updates as the decision pipeline processes.
    
    Args:
        request: Decision request with user_id and message
        db: Database session
        
    Returns:
        StreamingResponse with SSE events
    """
    return StreamingResponse(
        stream_decision(db, request.user_id, request.message),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.get("/decisions/{user_id}")
async def get_user_decisions(
    user_id: str,
    limit: int = 10,
    db: Session = Depends(get_db)
):
    """
    Get decision history for a user.
    
    Args:
        user_id: User identifier
        limit: Maximum number of decisions to return
        db: Database session
        
    Returns:
        List of past decisions
    """
    user = db.query(User).filter_by(user_id=user_id).first()
    
    if not user:
        return {"decisions": [], "count": 0}
    
    decisions = db.query(Decision).filter(
        Decision.user_id == user.id
    ).order_by(Decision.created_at.desc()).limit(limit).all()
    
    return {
        "decisions": [
            {
                "id": d.id,
                "input_message": d.input_message,
                "action_taken": d.action_taken,
                "confidence": d.confidence_score,
                "created_at": d.created_at.isoformat()
            }
            for d in decisions
        ],
        "count": len(decisions)
    }


@router.get("/decision/{decision_id}")
async def get_decision_detail(
    decision_id: int,
    db: Session = Depends(get_db)
):
    """
    Get detailed information about a specific decision.
    
    Args:
        decision_id: Decision ID
        db: Database session
        
    Returns:
        Detailed decision information
    """
    decision = db.query(Decision).filter(Decision.id == decision_id).first()
    
    if not decision:
        raise HTTPException(status_code=404, detail="Decision not found")
    
    return {
        "id": decision.id,
        "input_message": decision.input_message,
        "extracted_data": json.loads(decision.extracted_data) if decision.extracted_data else None,
        "task_analysis": json.loads(decision.task_analysis) if decision.task_analysis else None,
        "calendar_result": json.loads(decision.calendar_result) if decision.calendar_result else None,
        "scenarios": json.loads(decision.scenarios) if decision.scenarios else None,
        "final_decision": json.loads(decision.final_decision) if decision.final_decision else None,
        "action_taken": decision.action_taken,
        "confidence": decision.confidence_score,
        "created_at": decision.created_at.isoformat()
    }


@router.get("/events/{user_id}")
async def get_user_events(
    user_id: str,
    db: Session = Depends(get_db)
):
    """
    Get calendar events for a user.
    
    Args:
        user_id: User identifier
        db: Database session
        
    Returns:
        List of calendar events
    """
    user = get_or_create_user(db, user_id)
    
    events = db.query(CalendarEvent).filter(
        CalendarEvent.user_id == user.id,
        CalendarEvent.status != "cancelled"
    ).order_by(CalendarEvent.start_time).all()
    
    return {
        "events": [
            {
                "event_id": e.event_id,
                "title": e.title,
                "description": e.description,
                "start_time": e.start_time.isoformat(),
                "end_time": e.end_time.isoformat(),
                "status": e.status
            }
            for e in events
        ],
        "count": len(events)
    }


@router.post("/events/{user_id}")
async def create_event(
    user_id: str,
    event: EventCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new calendar event.
    
    Args:
        user_id: User identifier
        event: Event creation data
        db: Database session
        
    Returns:
        Created event details
    """
    from backend.tools.mcp_tools import MCPTools
    
    mcp = MCPTools(db, user_id)
    result = mcp.create_event(
        title=event.title,
        description=event.description,
        start_time=event.start_time,
        end_time=event.end_time
    )
    
    return result


@router.get("/tasks/{user_id}")
async def get_user_tasks(
    user_id: str,
    db: Session = Depends(get_db)
):
    """
    Get tasks for a user.
    
    Args:
        user_id: User identifier
        db: Database session
        
    Returns:
        List of tasks
    """
    user = get_or_create_user(db, user_id)
    
    tasks = db.query(Task).filter(
        Task.user_id == user.id,
        Task.status != "cancelled"
    ).order_by(Task.priority.desc()).all()
    
    return {
        "tasks": [
            {
                "task_id": t.task_id,
                "title": t.title,
                "description": t.description,
                "priority": t.priority,
                "deadline": t.deadline.isoformat() if t.deadline else None,
                "status": t.status
            }
            for t in tasks
        ],
        "count": len(tasks)
    }


@router.post("/tasks/{user_id}")
async def create_task(
    user_id: str,
    task: TaskCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new task.
    
    Args:
        user_id: User identifier
        task: Task creation data
        db: Database session
        
    Returns:
        Created task details
    """
    from backend.tools.mcp_tools import MCPTools
    
    mcp = MCPTools(db, user_id)
    result = mcp.add_task(
        title=task.title,
        description=task.description,
        priority=task.priority,
        deadline=task.deadline,
        estimated_duration=task.estimated_duration
    )
    
    return result


@router.get("/health")
async def health_check():
    """
    Health check endpoint.
    
    Returns:
        Health status
    """
    return {
        "status": "healthy",
        "service": "DecisionOS",
        "version": "1.0.0"
    }


# ============================================================
# Google Calendar Integration Endpoints
# ============================================================

@router.get("/calendar/status")
async def google_calendar_status(
    user_id: str = Query(default="user_001"),
    db: Session = Depends(get_db)
):
    """
    Check Google Calendar integration status.
    
    Returns:
        Integration status and authentication state
    """
    available = is_google_calendar_available()
    credentials_exist = CREDENTIALS_FILE.exists()
    token_exists = False
    try:
        user = get_or_create_user(db, user_id)
        token_exists = db.query(GoogleCalendarToken).filter(GoogleCalendarToken.user_id == user.id).first() is not None
    except OperationalError:
        db.rollback()
    
    authenticated = False
    error = None
    
    if available:
        try:
            service = get_google_calendar_service()
            authenticated = service.authenticate(user_id=user_id, db=db, interactive=False)
            if not authenticated:
                error = service.error_message
        except Exception as e:
            error = str(e)
    
    return {
        "google_calendar_available": available,
        "credentials_file_exists": credentials_exist,
        "credentials_file_path": str(CREDENTIALS_FILE),
        "token_exists": token_exists,
        "token_file_exists": token_exists,
        "authenticated": authenticated,
        "error": error,
        "instructions": None if authenticated else (
            "To enable Google Calendar:\n"
            "1. Go to Google Cloud Console\n"
            "2. Create a project and enable Calendar API\n"
            "3. Create OAuth 2.0 credentials (Web application)\n"
            f"4. Local option: place credentials.json at: {CREDENTIALS_FILE}\n"
            "5. Cloud option: set GOOGLE_CREDENTIALS_JSON env var to the OAuth client JSON\n"
            "6. Call /api/calendar/auth to authenticate"
        )
    }


def _build_callback_url(request: Request) -> str:
    """Construct absolute callback URL, handling Cloud Run reverse proxy."""
    # Cloud Run sets these headers for reverse proxy
    forwarded_proto = request.headers.get("x-forwarded-proto", "https")
    forwarded_host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    
    if forwarded_host and forwarded_proto:
        return f"{forwarded_proto}://{forwarded_host}/api/calendar/oauth/callback"
    
    # Fallback to request.url_for if headers not available
    try:
        callback = str(request.url_for("google_calendar_oauth_callback"))
        if callback.startswith("http"):
            return callback
        # If relative, build absolute with request base URL
        base_url = str(request.base_url).rstrip("/")
        return base_url + callback
    except Exception:
        # Last resort: use localhost for local dev
        return "http://localhost:8000/api/calendar/oauth/callback"


@router.get("/calendar/auth")
async def google_calendar_authenticate(
    request: Request,
    user_id: str = Query(default="user_001"),
    db: Session = Depends(get_db)
):
    """
    Trigger Google Calendar OAuth authentication.
    Opens browser for user consent.
    
    Returns:
        Authentication result
    """
    if not is_google_calendar_available():
        raise HTTPException(
            status_code=503,
            detail=(
                "Google Calendar not available. Provide credentials.json at "
                f"{CREDENTIALS_FILE} or set GOOGLE_CREDENTIALS_JSON env var."
            )
        )
    
    try:
        service = get_google_calendar_service()
        redirect_uri = _build_callback_url(request)
        auth_url = service.get_auth_url(redirect_uri, user_id=user_id, db=db)
        if not auth_url:
            raise HTTPException(status_code=400, detail=f"Failed to start OAuth: {service.error_message}")
        return RedirectResponse(url=auth_url, status_code=307)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Authentication error: {str(e)}"
        )


@router.get("/calendar/oauth/callback", name="google_calendar_oauth_callback")
async def google_calendar_oauth_callback(
    request: Request,
    code: str = Query(default=""),
    state: str = Query(default="user_001"),
    db: Session = Depends(get_db)
):
    """OAuth callback endpoint for Google Calendar web flow."""
    if not code:
        raise HTTPException(status_code=400, detail="Missing OAuth code")

    service = get_google_calendar_service()
    redirect_uri = _build_callback_url(request)
    success = service.complete_web_oauth(code=code, redirect_uri=redirect_uri, user_id=state, db=db)

    if not success:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {service.error_message}")

    # Popup-friendly completion page
    return HTMLResponse(
        content=(
            "<html><body><script>"
            "window.opener && window.opener.postMessage({ type: 'google-calendar-auth', success: true }, '*');"
            "window.close();"
            "</script><p>Google Calendar connected. You can close this window.</p></body></html>"
        )
    )

@router.get("/calendar/auth_url")
async def google_calendar_auth_url(user_id: str = Query(default="user_001")):
    """
    Return backend URL used by frontend to trigger OAuth flow.
    """
    return {
        "auth_url": f"/api/calendar/auth?user_id={user_id}"
    }


@router.get("/calendar/events")
async def get_google_calendar_events(
    hours: int = 24,
    user_id: str = "system",
    db: Session = Depends(get_db)
):
    """
    Get events from Google Calendar (or DB fallback).
    
    Args:
        hours: Number of hours to look ahead (default: 24)
        db: Database session
        
    Returns:
        List of calendar events with source info
    """
    from backend.tools.mcp_tools import MCPTools
    service = get_google_calendar_service() if is_google_calendar_available() else None
    authenticated = False
    if service is not None:
        try:
            authenticated = service.authenticate(user_id=user_id, db=db, interactive=False)
        except Exception:
            authenticated = False
    
    mcp = MCPTools(db, user_id)
    
    now = datetime.now()
    start = now
    end = now + timedelta(hours=max(hours, 1))
    
    events, source = mcp.get_events_in_range(start, end)
    
    # Serialize events
    serialized = []
    for e in events:
        event_data = {}
        for key, value in e.items():
            if isinstance(value, datetime):
                event_data[key] = value.isoformat()
            else:
                event_data[key] = value
        serialized.append(event_data)
    
    return {
        "events": serialized,
        "count": len(events),
        "source": source,
        "authenticated": authenticated,
        "user_id": user_id,
        "time_window": {
            "start": start.isoformat(),
            "end": end.isoformat()
        }
    }


@router.post("/prioritize")
async def prioritize_day(
    request: PrioritizeRequest,
    db: Session = Depends(get_db)
):
    """
    Build a practical daily plan using tasks plus real calendar events.
    """
    from backend.tools.mcp_tools import MCPTools

    mcp = MCPTools(db, request.user_id)
    now = datetime.now()
    day_end = now.replace(hour=22, minute=0, second=0, microsecond=0)

    events, _source = mcp.get_events_in_range(now, day_end)
    normalized_events = []
    for event in events:
        start_time = _parse_datetime(event.get("start_time"))
        end_time = _parse_datetime(event.get("end_time"))
        if start_time and end_time and end_time > start_time:
            normalized_events.append((start_time, end_time))
    normalized_events.sort(key=lambda slot: slot[0])

    cursor = now
    plan = []
    task_duration = timedelta(minutes=60)

    for task in request.tasks:
        while True:
            conflict = None
            for start_time, end_time in normalized_events:
                if cursor < end_time and (cursor + task_duration) > start_time:
                    conflict = (start_time, end_time)
                    break
            if conflict is None:
                break
            cursor = conflict[1] + timedelta(minutes=15)

        if cursor + task_duration > day_end:
            break

        slot_end = cursor + task_duration
        plan.append(
            {
                "task": task,
                "start": cursor.strftime("%I:%M %p"),
                "end": slot_end.strftime("%I:%M %p"),
                "note": "Scheduled around existing calendar events",
            }
        )
        cursor = slot_end + timedelta(minutes=15)

    return {
        "plan": plan,
        "count": len(plan),
        "calendar_event_count": len(normalized_events),
    }


@router.post("/prioritize_tasks")
async def prioritize_tasks_only(
    request: TaskPrioritizeRequest,
    db: Session = Depends(get_db)
):
    """Prioritize a plain list of tasks using Vertex AI Gemini and return simple JSON output."""
    # NOTE: keep endpoint simple for Postman demos while still leveraging user calendar context.
    tasks = [task.strip() for task in request.tasks if isinstance(task, str) and task.strip()]
    if not tasks:
        raise HTTPException(status_code=400, detail="tasks must contain at least one non-empty task")

    # Pull upcoming events to avoid generic prioritization and include real constraints.
    calendar_events = _get_upcoming_calendar_context(db, request.user_id)

    return await _prioritize_tasks_with_vertex(tasks, calendar_events)


# ============================================================
# Action Execution Endpoint
# ============================================================

@router.post("/execute_action")
async def execute_action(
    request: ExecuteActionRequest,
    db: Session = Depends(get_db)
):
    """
    Execute an action via MCP tools.
    
    This endpoint is called when user clicks an action button
    after reviewing the decision.
    
    Flow:
    1. User clicks action button
    2. Frontend shows confirmation popup
    3. User confirms
    4. This endpoint executes via MCP
    5. Updates calendar + DB
    6. Returns success message
    
    Args:
        request: ExecuteActionRequest with action details
        db: Database session
        
    Returns:
        Execution result with success status and message
    """
    from backend.tools.mcp_tools import MCPTools
    
    mcp = MCPTools(db, request.user_id)
    
    action_type = request.action_type.lower()
    event_id = request.event_id
    params = request.params
    
    result = {
        "success": False,
        "action_type": action_type,
        "message": "Unknown action type"
    }
    
    try:
        if action_type in ["cancel_event", "skip"]:
            # Skip/cancel an event
            if not event_id:
                return {"success": False, "message": "Event ID required for cancel action"}
            result = mcp.cancel_event(event_id)
            
        elif action_type == "reschedule_event":
            # Reschedule an event
            if not event_id:
                return {"success": False, "message": "Event ID required for reschedule action"}
            existing_event = db.query(CalendarEvent).filter(
                CalendarEvent.event_id == event_id,
                CalendarEvent.user_id == mcp.user.id
            ).first()

            new_start = _parse_datetime(params.get("new_start_time"))
            new_end = _parse_datetime(params.get("new_end_time"))

            suggested_start = _parse_datetime(params.get("suggested_time"))

            if suggested_start and not new_start:
                new_start = suggested_start

            if new_start and not new_end:
                event = db.query(CalendarEvent).filter(CalendarEvent.event_id == event_id).first()
                if event and event.end_time and event.start_time:
                    original_duration = event.end_time - event.start_time
                    new_end = new_start + original_duration
                else:
                    new_end = new_start + timedelta(hours=1)

            if not new_start or not new_end:
                # Default: reschedule to 2 hours later
                event = existing_event or db.query(CalendarEvent).filter(CalendarEvent.event_id == event_id).first()
                if event:
                    new_start = event.start_time + timedelta(hours=2)
                    new_end = event.end_time + timedelta(hours=2)
                else:
                    return {"success": False, "message": "Event not found and no new time provided"}
            result = mcp.reschedule_event(event_id, new_start, new_end)

            focus_title = (params.get("create_focus_event_title") or "").strip()
            if result.get("success") and focus_title and existing_event:
                focus_result = mcp.create_event(
                    title=focus_title,
                    start_time=existing_event.start_time,
                    end_time=existing_event.end_time,
                    description="Auto-created focus block after rescheduling a conflicting event",
                )
                result["focus_event"] = {
                    "created": bool(focus_result.get("success")),
                    "event_id": focus_result.get("event_id"),
                    "title": focus_result.get("title"),
                }
            
        elif action_type == "create_event":
            # Create a new event
            title = params.get("title", "New Event")
            start_time = _parse_datetime(params.get("start_time"))
            end_time = _parse_datetime(params.get("end_time"))
            description = params.get("description")
            if not start_time or not end_time:
                return {"success": False, "message": "Start and end time required for create action"}
            result = mcp.create_event(title, start_time, end_time, description)
            
        elif action_type == "add_task":
            # Add a task
            title = params.get("title", "New Task")
            description = params.get("description")
            priority = params.get("priority", 5)
            deadline = _parse_datetime(params.get("deadline"))
            duration = params.get("estimated_duration")
            result = mcp.add_task(title, description, priority, deadline, duration)
            
        else:
            result = {
                "success": True,
                "action_type": action_type,
                "message": f"Action '{action_type}' acknowledged (no MCP execution needed)"
            }
            
    except Exception as e:
        result = {
            "success": False,
            "action_type": action_type,
            "message": f"Error executing action: {str(e)}"
        }
    
    return result


# ============================================================
# Decision History & Learning Signal
# ============================================================

@router.get("/decisions/{user_id}/similar")
async def get_similar_decisions(
    user_id: str,
    task_type: Optional[str] = None,
    limit: int = 5,
    db: Session = Depends(get_db)
):
    """
    Get similar past decisions for learning signal.
    
    Args:
        user_id: User identifier
        task_type: Optional task type to filter by
        limit: Maximum decisions to return
        db: Database session
        
    Returns:
        List of similar past decisions with patterns
    """
    user = db.query(User).filter(User.user_id == user_id).first()
    
    if not user:
        return {"decisions": [], "pattern": None, "count": 0}
    
    # Query past decisions
    query = db.query(Decision).filter(Decision.user_id == user.id)
    
    if task_type:
        query = query.filter(Decision.input_message.ilike(f"%{task_type}%"))
    
    decisions = query.order_by(Decision.created_at.desc()).limit(limit).all()
    
    # Analyze patterns
    action_counts = {}
    for d in decisions:
        action = d.action_taken or "unknown"
        action_counts[action] = action_counts.get(action, 0) + 1
    
    most_common_action = max(action_counts, key=action_counts.get) if action_counts else None
    
    return {
        "decisions": [
            {
                "id": d.id,
                "input": d.input_message[:100] + "..." if len(d.input_message) > 100 else d.input_message,
                "action": d.action_taken,
                "confidence": d.confidence_score,
                "created_at": d.created_at.isoformat()
            }
            for d in decisions
        ],
        "pattern": {
            "most_common_action": most_common_action,
            "action_counts": action_counts,
            "message": f"Based on {len(decisions)} similar past situations, you usually chose to {most_common_action}" if most_common_action else None
        },
        "count": len(decisions)
    }
