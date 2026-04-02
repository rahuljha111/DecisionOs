"""
API Routes for DecisionOS.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta
import json

from backend.db.database import get_db, Decision, CalendarEvent, Task, get_or_create_user, User
from backend.schemas import DecisionRequest, EventCreate, TaskCreate, ExecuteActionRequest
from ai_engine.orchestrator import stream_decision
from backend.tools.google_calendar import (
    get_google_calendar_service,
    is_google_calendar_available,
    CREDENTIALS_FILE,
    TOKEN_FILE
)

router = APIRouter()


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
    user = db.query(get_or_create_user.__wrapped__(db, user_id).__class__).filter_by(user_id=user_id).first()
    
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
async def google_calendar_status():
    """
    Check Google Calendar integration status.
    
    Returns:
        Integration status and authentication state
    """
    available = is_google_calendar_available()
    credentials_exist = CREDENTIALS_FILE.exists()
    token_exists = TOKEN_FILE.exists()
    
    authenticated = False
    error = None
    
    if available:
        try:
            service = get_google_calendar_service()
            authenticated = service.authenticate()
            if not authenticated:
                error = service.error_message
        except Exception as e:
            error = str(e)
    
    return {
        "google_calendar_available": available,
        "credentials_file_exists": credentials_exist,
        "credentials_file_path": str(CREDENTIALS_FILE),
        "token_file_exists": token_exists,
        "authenticated": authenticated,
        "error": error,
        "instructions": None if authenticated else (
            "To enable Google Calendar:\n"
            "1. Go to Google Cloud Console\n"
            "2. Create a project and enable Calendar API\n"
            "3. Create OAuth 2.0 credentials (Desktop app)\n"
            f"4. Download credentials.json to: {CREDENTIALS_FILE}\n"
            "5. Call /api/calendar/auth to authenticate"
        )
    }


@router.get("/calendar/auth")
async def google_calendar_authenticate():
    """
    Trigger Google Calendar OAuth authentication.
    Opens browser for user consent.
    
    Returns:
        Authentication result
    """
    if not is_google_calendar_available():
        raise HTTPException(
            status_code=503,
            detail=f"Google Calendar not available. Place credentials.json at: {CREDENTIALS_FILE}"
        )
    
    try:
        service = get_google_calendar_service()
        success = service.authenticate()
        
        if success:
            return {
                "success": True,
                "message": "Google Calendar authenticated successfully!",
                "token_saved": TOKEN_FILE.exists()
            }
        else:
            raise HTTPException(
                status_code=401,
                detail=f"Authentication failed: {service.error_message}"
            )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Authentication error: {str(e)}"
        )


@router.get("/calendar/events")
async def get_google_calendar_events(
    hours: int = 24,
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
    
    mcp = MCPTools(db, "system")
    
    now = datetime.now()
    end = now + timedelta(hours=hours)
    
    events, source = mcp.get_events_in_range(now, end)
    
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
        "time_window": {
            "start": now.isoformat(),
            "end": end.isoformat()
        }
    }


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
            new_start = params.get("new_start_time")
            new_end = params.get("new_end_time")
            if not new_start or not new_end:
                # Default: reschedule to 2 hours later
                event = db.query(CalendarEvent).filter(CalendarEvent.event_id == event_id).first()
                if event:
                    new_start = event.start_time + timedelta(hours=2)
                    new_end = event.end_time + timedelta(hours=2)
                else:
                    return {"success": False, "message": "Event not found and no new time provided"}
            result = mcp.reschedule_event(event_id, new_start, new_end)
            
        elif action_type == "create_event":
            # Create a new event
            title = params.get("title", "New Event")
            start_time = params.get("start_time")
            end_time = params.get("end_time")
            description = params.get("description")
            if not start_time or not end_time:
                return {"success": False, "message": "Start and end time required for create action"}
            result = mcp.create_event(title, start_time, end_time, description)
            
        elif action_type == "add_task":
            # Add a task
            title = params.get("title", "New Task")
            description = params.get("description")
            priority = params.get("priority", 5)
            deadline = params.get("deadline")
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
