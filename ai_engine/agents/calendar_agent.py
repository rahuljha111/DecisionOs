"""
Calendar Agent for DecisionOS.
RULE-BASED agent using REAL events from Google Calendar or database.
NO LLM usage. NO fake/default values.

Primary source: Google Calendar
Fallback: Database events table.

STRICT CONFLICT RULES:
- Overlap: (start_A < end_B) AND (end_A > start_B)
- Buffer: end_A + 30min > start_B
- Any conflict MUST trigger scenario analysis
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session

from ai_engine.config.defaults import (
    BUFFER_TIME, 
    EVENT_BUFFER_MINUTES,
    classify_event_priority,
    is_high_priority_task,
    is_low_priority_event
)
from backend.tools.mcp_tools import MCPTools


class CalendarAgentError(Exception):
    """Raised when calendar agent cannot compute valid result."""
    pass


def _normalize_datetime(dt: Any) -> Optional[datetime]:
    """
    Normalize datetime to naive (no timezone) for comparison.
    Google Calendar returns timezone-aware, local times are naive.
    """
    if dt is None:
        return None
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        except:
            return None
    if hasattr(dt, 'tzinfo') and dt.tzinfo is not None:
        # ✅ FIXED
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def run_calendar_agent(
    db: Session,
    user_id: str,
    time_context: Dict[str, Any],
    task_analysis: Dict[str, Any],
    extracted_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Analyze calendar conflicts using REAL events from Google Calendar or database.
    
    STRICT REQUIREMENTS:
    - MUST fetch real events (Google Calendar primary, DB fallback)
    - MUST compute real available_time from actual events
    - MUST detect real conflicts based on stored events
    - NO fake values allowed
    
    Args:
        db: Database session
        user_id: User identifier
        time_context: Output from time resolver
        task_analysis: Output from task agent
        extracted_data: Output from planner agent (with defaults)
        
    Returns:
        Dictionary with REAL computed values from events
        
    Raises:
        CalendarAgentError: If required data is missing
    """
    # Initialize MCP tools to access calendar
    mcp = MCPTools(db, user_id)
    
    # Extract time values
    current_time = time_context.get("current_time")
    if not current_time:
        current_time = datetime.now()
    
    deadline = time_context.get("deadline")
    
    # Get required time from task analysis
    required_time = task_analysis.get("estimated_duration")
    if required_time is None:
        required_time = extracted_data.get("estimated_duration", 2.0)
    
    buffer_time = extracted_data.get("buffer_time", BUFFER_TIME)
    total_required = required_time + buffer_time
    
    # Define time window: now until deadline (or 24h if no deadline)
    if deadline:
        window_end = deadline
    else:
        window_end = current_time + timedelta(hours=24)
    
    # FETCH REAL EVENTS FROM GOOGLE CALENDAR OR DATABASE
    db_events, events_source = mcp.get_events_in_range(current_time, window_end)
    
    # Also check for events mentioned in user input (synthetic event from time resolver)
    input_event = _extract_input_event(time_context, extracted_data)
    
    # Calculate REAL available time
    available_time, blocked_periods = _calculate_available_time_from_events(
        current_time=current_time,
        window_end=window_end,
        db_events=db_events,
        input_event=input_event
    )
    
    # Detect REAL conflicts
    has_conflict, conflict_reason, conflicting_events = _detect_conflicts(
        available_time=available_time,
        total_required=total_required,
        required_time=required_time,
        db_events=db_events,
        input_event=input_event,
        current_time=current_time,
        deadline=deadline
    )
    
    # Get primary event for alternatives
    primary_event = _get_primary_event(db_events, input_event, current_time)
    event_type = primary_event.get("title", "event").lower() if primary_event else \
                 extracted_data.get("event_type", "event")
    
    # Generate alternatives based on REAL situation
    alternatives = _generate_alternatives_with_events(
        has_conflict=has_conflict,
        primary_event=primary_event,
        event_type=event_type,
        urgency=task_analysis.get("urgency_score", 5),
        deadline=deadline
    )
    
    # Serialize db_events for JSON response
    serialized_events = _serialize_events(db_events)
    serialized_primary = _serialize_event(primary_event) if primary_event else None
    
    # Classify priorities
    task_type = extracted_data.get("task_type", "")
    task_priority = classify_event_priority(task_type)
    event_priority = classify_event_priority(event_type) if event_type else "medium"
    
    # Check for event overlaps (STRICT)
    all_events = list(db_events)
    if input_event:
        all_events.append(input_event)
    
    overlap_detected, overlap_details = _detect_event_overlaps(all_events, current_time)
    
    # Force conflict if overlap detected
    if overlap_detected and not has_conflict:
        has_conflict = True
        conflict_reason = overlap_details
    
    return {
        "available_time": round(available_time, 2),
        "required_time": round(required_time, 2),
        "buffer_time": buffer_time,
        "total_required": round(total_required, 2),
        "has_conflict": has_conflict,
        "conflict_reason": conflict_reason,
        "alternatives": alternatives,
        "event_type": event_type,
        "event_duration": primary_event.get("duration_hours", 1.0) if primary_event else 1.0,
        "db_events": serialized_events,  # REAL events from Google/DB
        "db_event_count": len(db_events),
        "conflicting_events": conflicting_events,
        "primary_event": serialized_primary,
        "blocked_periods": blocked_periods,
        "computed": True,
        "data_source": events_source,  # "google_calendar" or "database"
        # Priority classifications (CRITICAL for decision engine)
        "task_priority": task_priority,
        "event_priority": event_priority,
        "overlap_detected": overlap_detected,
        "force_scenario": has_conflict  # MUST trigger scenario agent
    }


def _serialize_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Serialize events list with datetime conversion."""
    return [_serialize_event(e) for e in events]


def _serialize_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """Serialize single event with datetime conversion."""
    result = {}
    for key, value in event.items():
        if isinstance(value, datetime):
            result[key] = value.isoformat()
        else:
            result[key] = value
    return result


def _detect_event_overlaps(
    events: List[Dict[str, Any]],
    current_time: datetime
) -> tuple:
    """
    STRICT overlap detection between events.
    
    Rules:
    - Direct overlap: (start_A < end_B) AND (end_A > start_B)
    - Buffer violation: end_A + 30min > start_B
    - Boundary touching: end_A == start_B (no buffer)
    
    Returns:
        Tuple of (has_overlap, overlap_details)
    """
    if len(events) < 2:
        return False, None
    
    buffer_minutes = EVENT_BUFFER_MINUTES
    overlaps = []
    
    # Sort events by start time
    sorted_events = sorted(
        events,
        key=lambda e: _normalize_datetime(e.get("start_time")) or datetime.max
    )
    
    for i in range(len(sorted_events)):
        for j in range(i + 1, len(sorted_events)):
            event_a = sorted_events[i]
            event_b = sorted_events[j]
            
            start_a = _normalize_datetime(event_a.get("start_time"))
            end_a = _normalize_datetime(event_a.get("end_time"))
            start_b = _normalize_datetime(event_b.get("start_time"))
            end_b = _normalize_datetime(event_b.get("end_time"))
            
            if not all([start_a, end_a, start_b, end_b]):
                continue
            
            # Check direct overlap: (start_A < end_B) AND (end_A > start_B)
            if start_a < end_b and end_a > start_b:
                overlaps.append({
                    "type": "direct_overlap",
                    "event_a": event_a.get("title"),
                    "event_b": event_b.get("title"),
                    "detail": f"'{event_a.get('title')}' overlaps with '{event_b.get('title')}'"
                })
                continue
            
            # Check boundary touching: end_A == start_B
            if end_a == start_b:
                overlaps.append({
                    "type": "boundary_touch",
                    "event_a": event_a.get("title"),
                    "event_b": event_b.get("title"),
                    "detail": f"'{event_a.get('title')}' ends exactly when '{event_b.get('title')}' starts (no buffer)"
                })
                continue
            
            # Check buffer violation: end_A + buffer > start_B
            end_a_with_buffer = end_a + timedelta(minutes=buffer_minutes)
            if end_a_with_buffer > start_b:
                gap_minutes = (start_b - end_a).total_seconds() / 60
                overlaps.append({
                    "type": "buffer_violation",
                    "event_a": event_a.get("title"),
                    "event_b": event_b.get("title"),
                    "gap_minutes": gap_minutes,
                    "detail": f"Only {int(gap_minutes)}min gap between '{event_a.get('title')}' and '{event_b.get('title')}' (need {buffer_minutes}min)"
                })
    
    if overlaps:
        details = "; ".join([o["detail"] for o in overlaps])
        return True, f"Event conflicts: {details}"
    
    return False, None


def _extract_input_event(
    time_context: Dict[str, Any],
    extracted_data: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """
    Extract event mentioned in user input (may not be in DB yet).
    E.g., "I have gym now" creates a synthetic event.
    """
    event_start = time_context.get("event_start") or time_context.get("meeting_start")
    event_end = time_context.get("event_end") or time_context.get("meeting_end")
    event_type = time_context.get("event_type") or extracted_data.get("event_type")
    
    if event_start:
        duration = time_context.get("event_duration", 1.0)
        if not event_end:
            event_end = event_start + timedelta(hours=duration)
        
        return {
            "event_id": "input_event",
            "title": event_type or "event",
            "start_time": event_start,
            "end_time": event_end,
            "duration_hours": duration,
            "source": "user_input"
        }
    
    return None


def _calculate_available_time_from_events(
    current_time: datetime,
    window_end: datetime,
    db_events: List[Dict[str, Any]],
    input_event: Optional[Dict[str, Any]]
) -> tuple:

    current_time = _normalize_datetime(current_time) or datetime.now()
    window_end = _normalize_datetime(window_end) or (current_time + timedelta(hours=24))

    total_hours = (window_end - current_time).total_seconds() / 3600
    if total_hours <= 0:
        return 0.0, []

    all_events = list(db_events)
    if input_event:
        is_duplicate = any(_events_overlap(input_event, e) for e in db_events)
        if not is_duplicate:
            all_events.append(input_event)

    # ✅ FIX: collect intervals first
    intervals = []
    blocked_periods = []

    for event in all_events:
        event_start = _normalize_datetime(event.get("start_time"))
        event_end = _normalize_datetime(event.get("end_time"))

        if event_start and event_end:
            clip_start = max(event_start, current_time)
            clip_end = min(event_end, window_end)

            if clip_start < clip_end:
                intervals.append((clip_start, clip_end))
                blocked_periods.append({
                    "event": event.get("title", "Unknown"),
                    "start": clip_start.isoformat(),
                    "end": clip_end.isoformat(),
                    "blocked_hours": round(
                        (clip_end - clip_start).total_seconds() / 3600, 2
                    )
                })

    # ✅ FIX: merge overlapping intervals
    merged = _merge_intervals(intervals)

    total_blocked = sum(
        (end - start).total_seconds() / 3600
        for start, end in merged
    )

    available = max(0, total_hours - total_blocked)
    return round(available, 2), blocked_periods


# ✅ NEW: merge intervals (prevents double counting)
def _merge_intervals(intervals):
    intervals.sort()
    merged = []
    for start, end in intervals:
        if not merged or merged[-1][1] < start:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return merged


def _events_overlap(event1: Dict[str, Any], event2: Dict[str, Any]) -> bool:
    """Check if two events overlap in time."""
    start1 = _normalize_datetime(event1.get("start_time"))
    end1 = _normalize_datetime(event1.get("end_time"))
    start2 = _normalize_datetime(event2.get("start_time"))
    end2 = _normalize_datetime(event2.get("end_time"))
    
    if not all([start1, end1, start2, end2]):
        return False
    
    return start1 < end2 and start2 < end1


def _detect_conflicts(
    available_time: float,
    total_required: float,
    required_time: float,
    db_events: List[Dict[str, Any]],
    input_event: Optional[Dict[str, Any]],
    current_time: datetime,
    deadline: datetime
) -> tuple:
    """
    Detect REAL conflicts based on events and time requirements.
    
    Returns:
        Tuple of (has_conflict, reason, conflicting_events)
    """
    # Normalize times
    current_time = _normalize_datetime(current_time) or datetime.now()
    deadline = _normalize_datetime(deadline)
    
    conflicting_events = []
    
    # PRIMARY: Insufficient time
    if available_time < total_required:
        deficit = total_required - available_time
        
        # Find which events cause the conflict
        all_events = list(db_events)
        if input_event:
            all_events.append(input_event)
        
        for event in all_events:
            if deadline:
                event_start = _normalize_datetime(event.get("start_time"))
                if event_start and event_start < deadline:
                    conflicting_events.append({
                        "event_id": event.get("event_id"),
                        "title": event.get("title"),
                        "blocks_hours": event.get("duration_hours", 1.0)
                    })
        
        return True, f"Time conflict: need {total_required:.1f}h but only {available_time:.1f}h available (deficit: {deficit:.1f}h)", conflicting_events
    
    # CHECK: Event happening NOW
    all_events = list(db_events)
    if input_event:
        all_events.append(input_event)
    
    for event in all_events:
        event_start = _normalize_datetime(event.get("start_time"))
        event_end = _normalize_datetime(event.get("end_time"))
        
        if event_start and event_end:
            # Event is NOW
            if event_start <= current_time < event_end:
                conflicting_events.append({
                    "event_id": event.get("event_id"),
                    "title": event.get("title"),
                    "status": "in_progress"
                })
                return True, f"'{event.get('title')}' is happening NOW - blocking work time", conflicting_events
            
            # Event starting very soon
            minutes_until = (event_start - current_time).total_seconds() / 60
            if 0 < minutes_until < 30:
                conflicting_events.append({
                    "event_id": event.get("event_id"),
                    "title": event.get("title"),
                    "starts_in_minutes": int(minutes_until)
                })
                return True, f"'{event.get('title')}' starts in {int(minutes_until)} minutes - immediate conflict", conflicting_events
    
    # CHECK: Tight margin
    if available_time < total_required * 1.2 and available_time > 0:
        margin = available_time - total_required
        return True, f"Tight schedule: only {margin:.1f}h buffer - high risk", conflicting_events
    
    return False, None, []


def _get_primary_event(
    db_events: List[Dict[str, Any]],
    input_event: Optional[Dict[str, Any]],
    current_time: datetime
) -> Optional[Dict[str, Any]]:
    """
    Get the most relevant upcoming or current event.
    """
    all_events = list(db_events)
    if input_event:
        all_events.append(input_event)

    if not all_events:
        return None

    def get_sort_key(e):
        st = _normalize_datetime(e.get("start_time"))
        return st if st else datetime.max

    sorted_events = sorted(all_events, key=get_sort_key)

    # ✅ FIX: prefer upcoming or ongoing event
    for e in sorted_events:
        st = _normalize_datetime(e.get("start_time"))
        en = _normalize_datetime(e.get("end_time"))

        if st and en:
            if st <= current_time < en:  # ongoing
                return e
            if st >= current_time:  # next upcoming
                return e

    return sorted_events[0]
    
 
def _generate_alternatives_with_events(
    has_conflict: bool,
    primary_event: Optional[Dict[str, Any]],
    event_type: str,
    urgency: float,
    deadline: datetime
) -> List[Dict[str, Any]]:
    """
    Generate alternatives with REAL event references.
    
    Returns list of alternatives with event_id for MCP execution.
    """
    event_name = event_type.lower() if event_type else "event"
    event_id = primary_event.get("event_id") if primary_event else None
    event_title = primary_event.get("title") if primary_event else event_name
    
    if not primary_event:
        if has_conflict:
            return [
                {"action": "prioritize_task", "description": "Focus on task immediately"},
                {"action": "extend_deadline", "description": "Request deadline extension"},
                {"action": "reduce_scope", "description": "Reduce task scope"}
            ]
        else:
            return [
                {"action": "proceed_as_planned", "description": "Continue with current plan"},
                {"action": "start_immediately", "description": "Begin task now"},
                {"action": "schedule_buffer", "description": "Add buffer time"}
            ]
    
    # Suggested reschedule time (after deadline if exists)
    reschedule_time = None
    if deadline:
        reschedule_time = (deadline + timedelta(hours=1)).isoformat()
    
    # Generate 3 alternatives with event references
    alternatives = []
    
    if has_conflict:
        if urgency >= 8:
            # High urgency - skip is best
            alternatives = [
                {
                    "action": f"skip_{event_name}",
                    "event_id": event_id,
                    "event_title": event_title,
                    "description": f"Skip {event_title} to focus on urgent task",
                    "mcp_action": "cancel_event" if event_id else None
                },
                {
                    "action": f"reschedule_{event_name}",
                    "event_id": event_id,
                    "event_title": event_title,
                    "description": f"Reschedule {event_title} to after deadline",
                    "suggested_time": reschedule_time,
                    "mcp_action": "reschedule_event" if event_id else None
                },
                {
                    "action": f"attend_{event_name}",
                    "event_id": event_id,
                    "event_title": event_title,
                    "description": f"Attend {event_title} despite conflict (risky)",
                    "mcp_action": None
                }
            ]
        elif urgency >= 6:
            # Moderate urgency - reschedule preferred
            alternatives = [
                {
                    "action": f"reschedule_{event_name}",
                    "event_id": event_id,
                    "event_title": event_title,
                    "description": f"Reschedule {event_title} to later",
                    "suggested_time": reschedule_time,
                    "mcp_action": "reschedule_event" if event_id else None
                },
                {
                    "action": f"skip_{event_name}",
                    "event_id": event_id,
                    "event_title": event_title,
                    "description": f"Skip {event_title} entirely",
                    "mcp_action": "cancel_event" if event_id else None
                },
                {
                    "action": f"attend_{event_name}",
                    "event_id": event_id,
                    "event_title": event_title,
                    "description": f"Attend {event_title} (may miss deadline)",
                    "mcp_action": None
                }
            ]
        else:
            # Lower urgency
            alternatives = [
                {
                    "action": f"reschedule_{event_name}",
                    "event_id": event_id,
                    "event_title": event_title,
                    "description": f"Reschedule {event_title} for flexibility",
                    "mcp_action": "reschedule_event" if event_id else None
                },
                {
                    "action": f"attend_{event_name}",
                    "event_id": event_id,
                    "event_title": event_title,
                    "description": f"Attend {event_title} then work on task",
                    "mcp_action": None
                },
                {
                    "action": f"skip_{event_name}",
                    "event_id": event_id,
                    "event_title": event_title,
                    "description": f"Skip {event_title} if needed",
                    "mcp_action": "cancel_event" if event_id else None
                }
            ]
    else:
        # No conflict
        alternatives = [
            {
                "action": f"attend_{event_name}",
                "event_id": event_id,
                "event_title": event_title,
                "description": f"Attend {event_title} as planned",
                "mcp_action": None
            },
            {
                "action": f"reschedule_{event_name}",
                "event_id": event_id,
                "event_title": event_title,
                "description": f"Reschedule {event_title} for more buffer",
                "mcp_action": "reschedule_event" if event_id else None
            },
            {
                "action": f"skip_{event_name}",
                "event_id": event_id,
                "event_title": event_title,
                "description": f"Skip {event_title} to start early",
                "mcp_action": "cancel_event" if event_id else None
            }
        ]
    
    return alternatives


def format_calendar_result(result: Dict[str, Any]) -> str:
    """Format calendar result for display."""
    lines = [
        f"📅 Data Source: {result.get('data_source', 'computed')}",
        f"📊 DB Events Found: {result.get('db_event_count', 0)}",
        f"⏱️ Available Time: {result['available_time']:.1f} hours",
        f"📋 Required Time: {result['required_time']:.1f} hours (+ {result['buffer_time']:.1f}h buffer)",
        f"⚠️ Conflict: {'Yes - ' + result['conflict_reason'] if result['has_conflict'] else 'No'}"
    ]
    
    if result.get('primary_event'):
        event = result['primary_event']
        lines.insert(1, f"🎯 Primary Event: {event.get('title', 'Unknown')}")
    
    if result.get('blocked_periods'):
        lines.append("🚫 Blocked Periods:")
        for bp in result['blocked_periods']:
            lines.append(f"   - {bp['event']}: {bp['blocked_hours']}h")
    
    return "\n".join(lines)
