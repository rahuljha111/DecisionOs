"""
DecisionOS - AI That Simulates Before It Decides

Main FastAPI application entry point.
"""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.db.database import init_db
from backend.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler.
    Initialize database on startup.
    """
    # Startup
    init_db()
    print("✓ Database initialized")
    print("✓ DecisionOS ready")
    
    yield
    
    # Shutdown
    print("DecisionOS shutting down...")


# Create FastAPI application
app = FastAPI(
    title="DecisionOS",
    description="AI That Simulates Before It Decides - A multi-agent decision engine",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router, prefix="/api")

# Serve static frontend files
frontend_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")

# Mount static files if frontend directory exists
if os.path.exists(frontend_path):
    app.mount("/static", StaticFiles(directory=frontend_path), name="static")
    
    @app.get("/")
    async def serve_frontend():
        """Serve the main frontend page."""
        return FileResponse(os.path.join(frontend_path, "index.html"))
    
    @app.get("/app.js")
    async def serve_js():
        """Serve the JavaScript file."""
        return FileResponse(
            os.path.join(frontend_path, "app.js"),
            media_type="application/javascript"
        )
    
    @app.get("/styles.css")
    async def serve_css():
        """Serve the CSS file."""
        return FileResponse(
            os.path.join(frontend_path, "styles.css"),
            media_type="text/css"
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )