"""
API Routes for DecisionOS.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse, RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError
from typing import List, Optional
from datetime import datetime, timedelta
import re
import json
from pydantic import BaseModel, Field

from backend.db.database import get_db, Decision, CalendarEvent, Task, get_or_create_user, User, GoogleCalendarToken
from backend.schemas import DecisionRequest, EventCreate, TaskCreate, ExecuteActionRequest
from ai_engine.orchestrator import stream_decision
from backend.tools.google_calendar import (
    get_google_calendar_service,
    is_google_calendar_available,
    CREDENTIALS_FILE
)

router = APIRouter()


class PrioritizeRequest(BaseModel):
    """Request schema for day prioritization."""
    user_id: str
    tasks: List[str] = Field(default_factory=list)
    meetings: List[dict] = Field(default_factory=list)


class TaskPrioritizeRequest(BaseModel):
    """Request schema for simple task prioritization demos."""
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


def _score_task_priority(task: str) -> tuple[int, str, str]:
    """Score a task string and return priority score, decision label, and reason."""
    text = (task or "").lower().strip()

    if not text:
        return 0, "Ignore empty task", "Empty tasks are not actionable"

    high_priority_keywords = ["interview", "exam", "deadline", "submission", "presentation", "meeting"]
    medium_priority_keywords = ["prepare", "report", "project", "assignment", "dinner", "dine", "cook"]
    low_priority_keywords = ["gym", "workout", "netflix", "watch", "movie", "game", "gaming", "scroll", "social"]

    if any(keyword in text for keyword in high_priority_keywords):
        if "interview" in text:
            return 100, "Attend interview", "Interview has highest priority and fixed time constraint"
        if "exam" in text:
            return 98, "Attend exam", "Exam has highest priority and fixed time constraint"
        if "deadline" in text or "submission" in text:
            return 95, "Finish deadline task", "Deadline-driven work takes priority over flexible items"
        return 90, "Handle high priority task", "High-priority work should be completed before flexible tasks"

    if any(keyword in text for keyword in medium_priority_keywords):
        if "dinner" in text or "cook" in text:
            return 70, "Prepare dinner", "Dinner is useful and time-sensitive, but still flexible"
        return 75, "Work on task", "This task is productive and should be completed before low-value activities"

    if any(keyword in text for keyword in low_priority_keywords):
        if "gym" in text or "workout" in text:
            return 40, "Go to gym", "Gym is healthy but usually flexible compared with fixed commitments"
        if "netflix" in text or "watch" in text or "movie" in text:
            return 10, "Watch entertainment", "Entertainment is lowest priority after essential tasks"
        return 20, "Do flexible activity", "Flexible activities should be placed after important work"

    return 60, "Work on task", "Default priority favors completing useful tasks before leisure"


def _task_label(task: str) -> str:
    """Convert a task sentence into a short label for decision text."""
    text = (task or "").strip()
    lower = text.lower()

    if "interview" in lower:
        return "interview"
    if "exam" in lower:
        return "exam"
    if "deadline" in lower or "submission" in lower:
        return "deadline task"
    if "gym" in lower or "workout" in lower:
        return "gym"
    if "netflix" in lower:
        return "Netflix"
    if "dinner" in lower or "cook" in lower:
        return "dinner"
    if "report" in lower:
        return "report"
    if "project" in lower:
        return "project"
    if "assignment" in lower:
        return "assignment"
    if "meeting" in lower:
        return "meeting"

    cleaned = re.sub(r"\bat\s+\d{1,2}(:\d{2})?\s*(am|pm)\b", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(today|tomorrow|tonight|later)\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.-")
    if not cleaned:
        return "task"
    return cleaned.lower()


def _has_explicit_time(task: str) -> bool:
    """Check whether a task contains a concrete time or day marker."""
    lower = (task or "").lower()
    return bool(
        re.search(r"\b\d{1,2}(:\d{2})?\s*(am|pm)\b", lower)
        or any(marker in lower for marker in ["today", "tomorrow", "tonight", "this evening", "this morning", "this afternoon"])
    )


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
        redirect_uri = str(request.url_for("google_calendar_oauth_callback"))
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
    redirect_uri = str(request.url_for("google_calendar_oauth_callback"))
    success = service.complete_web_oauth(code=code, redirect_uri=redirect_uri, user_id=state, db=db)

    if not success:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {service.error_message}")

    # Popup-friendly completion page
    return HTMLResponse(
        content=(
            "<html><body><script>"
            f"window.opener && window.opener.postMessage({{ type: 'google-calendar-auth', success: true, user_id: '{state}' }}, '*');"
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
async def prioritize_tasks_only(request: TaskPrioritizeRequest):
    """Prioritize a plain list of tasks for Postman demos."""
    scored_tasks = []

    for task in request.tasks:
        score, decision_label, reason = _score_task_priority(task)
        scored_tasks.append({
            "task": task,
            "score": score,
            "decision_label": decision_label,
            "reason": reason,
        })

    scored_tasks.sort(key=lambda item: item["score"], reverse=True)
    prioritized_tasks = [item["task"] for item in scored_tasks]

    decision = "No tasks provided"
    reason = "No tasks provided"

    if scored_tasks:
        top_task = scored_tasks[0]["task"]
        top_label = _task_label(top_task)
        top_score = scored_tasks[0]["score"]
        _, decision_label, reason = _score_task_priority(top_task)

        skip_candidate = None
        if len(scored_tasks) > 1:
            time_bound_candidates = [item for item in scored_tasks[1:] if _has_explicit_time(item["task"])]
            if time_bound_candidates:
                skip_candidate = time_bound_candidates[-1]
            else:
                skip_candidate = scored_tasks[-1]

        if top_score >= 90 and skip_candidate:
            skip_label = _task_label(skip_candidate["task"])
            decision = f"Attend {top_label} and skip {skip_label}"
        elif top_score >= 70:
            decision = f"Complete {top_label} first"
        else:
            decision = f"Work on {top_label} first"

        reason = reason if reason else f"{top_label} has the highest priority"

    return {
        "prioritized_tasks": prioritized_tasks,
        "decision": decision,
        "reason": reason,
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
