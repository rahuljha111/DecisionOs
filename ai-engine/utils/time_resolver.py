"""
Time Resolver for DecisionOS.
Robust deterministic time parsing using regex - NO LLM usage.
Handles: exam, gym, meeting, deadline, and various time expressions.
"""

import re
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple

from ai_engine.config.defaults import DEFAULT_MEETING_DURATION


def resolve_time_context(
    message: str, 
    base_time: Optional[datetime] = None,
    extracted_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Extract time context from user message using deterministic regex parsing.
    
    Parses:
    - 'in X hours' / 'in X hour' / 'in X hrs'
    - 'in X minutes' / 'in X mins'
    - 'now' (immediate)
    - 'today' / 'tomorrow'
    - Specific times like '3pm', '15:00'
    - Context-aware: exam times, gym times, meeting times
    
    Args:
        message: User's input message
        base_time: Base datetime (defaults to now)
        extracted_data: Optional extracted data from planner for context
        
    Returns:
        Dictionary with:
        - current_time: datetime
        - event_start: datetime or None (gym, meeting, etc.)
        - event_end: datetime or None
        - deadline: datetime or None (exam time, task deadline)
        - event_type: str or None
    """
    if base_time is None:
        base_time = datetime.now()
    
    message_lower = message.lower()
    
    result = {
        "current_time": base_time,
        "event_start": None,
        "event_end": None,
        "deadline": None,
        "event_type": None,
        "event_duration": 1.0  # default 1 hour
    }
    
    # Use extracted data if available
    if extracted_data:
        event_raw = extracted_data.get("event_raw")
        deadline_raw = extracted_data.get("deadline_raw")
        event_type = extracted_data.get("event_type")
        
        if event_raw:
            event_time = _parse_time_expression(event_raw, base_time)
            if event_time:
                result["event_start"] = event_time
                duration = _get_event_duration(event_type)
                result["event_end"] = event_time + timedelta(hours=duration)
                result["event_duration"] = duration
        
        if deadline_raw:
            deadline = _parse_time_expression(deadline_raw, base_time, is_deadline=True)
            if deadline:
                result["deadline"] = deadline
        
        if event_type:
            result["event_type"] = event_type
    
    # If not found via extracted data, parse from message directly
    if result["event_start"] is None:
        event_time, event_type = _parse_event_time(message_lower, base_time)
        if event_time:
            result["event_start"] = event_time
            duration = _get_event_duration(event_type)
            result["event_end"] = event_time + timedelta(hours=duration)
            result["event_type"] = event_type
            result["event_duration"] = duration
    
    if result["deadline"] is None:
        deadline = _parse_deadline_time(message_lower, base_time)
        if deadline:
            result["deadline"] = deadline
    
    # Legacy compatibility - also set meeting_start/meeting_end
    result["meeting_start"] = result["event_start"]
    result["meeting_end"] = result["event_end"]
    
    return result


def _parse_time_expression(
    time_str: str, 
    base_time: datetime,
    is_deadline: bool = False
) -> Optional[datetime]:
    """
    Parse a time expression string into datetime.
    
    Args:
        time_str: Time expression like "in 2 hours", "now", "tomorrow"
        base_time: Reference datetime
        is_deadline: If True, set time to end of day for date-only expressions
        
    Returns:
        Parsed datetime or None
    """
    if not time_str:
        return None
    
    time_str = time_str.lower().strip()
    
    # "now" or "right now"
    if time_str in ["now", "right now", "immediately"]:
        return base_time
    
    # "in X hours"
    match = re.search(r'in\s+(\d+(?:\.\d+)?)\s*(?:hours?|hrs?)', time_str)
    if match:
        hours = float(match.group(1))
        return base_time + timedelta(hours=hours)
    
    # "in X minutes"
    match = re.search(r'in\s+(\d+)\s*(?:minutes?|mins?)', time_str)
    if match:
        minutes = int(match.group(1))
        return base_time + timedelta(minutes=minutes)
    
    # Just "X hours" or "X hour" (without "in")
    match = re.search(r'^(\d+(?:\.\d+)?)\s*(?:hours?|hrs?)$', time_str)
    if match:
        hours = float(match.group(1))
        return base_time + timedelta(hours=hours)
    
    # "tomorrow"
    if "tomorrow" in time_str:
        tomorrow = base_time + timedelta(days=1)
        if is_deadline:
            return tomorrow.replace(hour=23, minute=59, second=59, microsecond=0)
        return tomorrow.replace(hour=9, minute=0, second=0, microsecond=0)
    
    # "today"
    if "today" in time_str:
        if is_deadline:
            return base_time.replace(hour=23, minute=59, second=59, microsecond=0)
        return base_time
    
    # Specific time "at Xpm" or "X:XX"
    match = re.search(r'(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?', time_str)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2)) if match.group(2) else 0
        meridiem = match.group(3)
        
        if meridiem == 'pm' and hour != 12:
            hour += 12
        elif meridiem == 'am' and hour == 12:
            hour = 0
        
        result_time = base_time.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        # If time is in the past, assume tomorrow
        if result_time < base_time:
            result_time += timedelta(days=1)
        
        return result_time
    
    return None


def _parse_event_time(message: str, base_time: datetime) -> Tuple[Optional[datetime], Optional[str]]:
    """
    Parse event/activity time from message (gym, meeting, appointment, etc.).
    
    Args:
        message: Lowercase message string
        base_time: Reference datetime
        
    Returns:
        Tuple of (event_datetime, event_type)
    """
    event_patterns = {
        "gym": r'(?:gym|workout|exercise)\s*(?:is\s+)?(?:in\s+(\d+)\s*(?:hours?|hrs?|minutes?|mins?)|now|starting)',
        "meeting": r'meeting\s*(?:is\s+)?(?:in\s+(\d+)\s*(?:hours?|hrs?|minutes?|mins?)|now|at\s+(\d+)(?::(\d+))?\s*(am|pm)?)',
        "appointment": r'appointment\s*(?:is\s+)?(?:in\s+(\d+)\s*(?:hours?|hrs?|minutes?|mins?)|now)',
        "call": r'call\s*(?:is\s+)?(?:in\s+(\d+)\s*(?:hours?|hrs?|minutes?|mins?)|now)',
        "class": r'class\s*(?:is\s+)?(?:in\s+(\d+)\s*(?:hours?|hrs?|minutes?|mins?)|now)',
    }
    
    for event_type, pattern in event_patterns.items():
        if event_type in message:
            # Check for "now"
            if f"{event_type} now" in message or f"have {event_type} now" in message or f"{event_type} is now" in message:
                return base_time, event_type
            
            match = re.search(pattern, message)
            if match:
                # Check for hour/minute values
                groups = match.groups()
                for g in groups:
                    if g and g.isdigit():
                        num = int(g)
                        if "hour" in message[match.start():match.end()+10] or "hr" in message[match.start():match.end()+10]:
                            return base_time + timedelta(hours=num), event_type
                        elif "minute" in message[match.start():match.end()+10] or "min" in message[match.start():match.end()+10]:
                            return base_time + timedelta(minutes=num), event_type
                
                # Default: assume "now" if event type mentioned without specific time
                return base_time, event_type
    
    # Generic "in X hours" without specific event type
    match = re.search(r'(?<!exam\s)(?<!test\s)in\s+(\d+)\s*(?:hours?|hrs?)', message)
    if match and not any(word in message for word in ["exam", "test", "deadline", "due"]):
        hours = int(match.group(1))
        return base_time + timedelta(hours=hours), "event"
    
    return None, None


def _parse_deadline_time(message: str, base_time: datetime) -> Optional[datetime]:
    """
    Parse deadline/exam time from message.
    
    Args:
        message: Lowercase message string
        base_time: Reference datetime
        
    Returns:
        Parsed deadline datetime or None
    """
    # Exam/test in X hours (this IS the deadline)
    match = re.search(r'(?:exam|test|quiz)\s+(?:is\s+)?in\s+(\d+)\s*(?:hours?|hrs?)', message)
    if match:
        hours = int(match.group(1))
        return base_time + timedelta(hours=hours)
    
    # Exam/test in X minutes
    match = re.search(r'(?:exam|test|quiz)\s+(?:is\s+)?in\s+(\d+)\s*(?:minutes?|mins?)', message)
    if match:
        minutes = int(match.group(1))
        return base_time + timedelta(minutes=minutes)
    
    # "deadline tomorrow" or "due tomorrow"
    if 'deadline tomorrow' in message or 'due tomorrow' in message or 'by tomorrow' in message:
        tomorrow = base_time + timedelta(days=1)
        return tomorrow.replace(hour=23, minute=59, second=59, microsecond=0)
    
    # "deadline today" or "due today"
    if 'deadline today' in message or 'due today' in message or 'by today' in message:
        return base_time.replace(hour=23, minute=59, second=59, microsecond=0)
    
    # "deadline in X hours"
    match = re.search(r'deadline\s+in\s+(\d+(?:\.\d+)?)\s*(?:hours?|hrs?)', message)
    if match:
        hours = float(match.group(1))
        return base_time + timedelta(hours=hours)
    
    # "deadline in X days"
    match = re.search(r'deadline\s+in\s+(\d+)\s*days?', message)
    if match:
        days = int(match.group(1))
        deadline = base_time + timedelta(days=days)
        return deadline.replace(hour=23, minute=59, second=59, microsecond=0)
    
    # Just "tomorrow" in context of task
    if 'tomorrow' in message and any(x in message for x in ['deadline', 'due', 'complete', 'finish', 'deliver', 'submit']):
        tomorrow = base_time + timedelta(days=1)
        return tomorrow.replace(hour=23, minute=59, second=59, microsecond=0)
    
    # "in X hours" in context of deadline (e.g., "project due in 5 hours")
    if any(x in message for x in ['deadline', 'due', 'submit']):
        match = re.search(r'in\s+(\d+)\s*(?:hours?|hrs?)', message)
        if match:
            hours = int(match.group(1))
            return base_time + timedelta(hours=hours)
    
    return None


def _get_event_duration(event_type: Optional[str]) -> float:
    """
    Get default duration for an event type.
    
    Args:
        event_type: Type of event
        
    Returns:
        Duration in hours
    """
    durations = {
        "gym": 1.5,
        "workout": 1.5,
        "exercise": 1.0,
        "meeting": 1.0,
        "appointment": 1.0,
        "call": 0.5,
        "class": 1.0,
        "lunch": 1.0,
        "dinner": 1.5,
    }
    return durations.get(event_type, DEFAULT_MEETING_DURATION)


def calculate_available_time(
    current_time: datetime,
    deadline: Optional[datetime],
    event_start: Optional[datetime] = None,
    event_end: Optional[datetime] = None
) -> float:
    """
    Calculate available working time before deadline, accounting for events.
    
    Args:
        current_time: Current datetime
        deadline: Deadline datetime
        event_start: Event start time (optional)
        event_end: Event end time (optional)
        
    Returns:
        Available hours
    """
    if deadline is None:
        # No deadline - but not infinite time, return reasonable work day
        return 8.0
    
    total_hours = (deadline - current_time).total_seconds() / 3600
    
    if total_hours < 0:
        return 0.0
    
    # Subtract event time if it falls before deadline
    if event_start and event_end and event_start < deadline:
        # Only subtract if event is between now and deadline
        if event_start >= current_time:
            event_hours = (event_end - event_start).total_seconds() / 3600
            total_hours -= event_hours
    
    return max(0, total_hours)


def format_time_for_display(dt: Optional[datetime]) -> str:
    """
    Format datetime for user-friendly display.
    
    Args:
        dt: Datetime to format
        
    Returns:
        Formatted string
    """
    if dt is None:
        return "Not specified"
    
    now = datetime.now()
    
    if dt.date() == now.date():
        return f"Today at {dt.strftime('%I:%M %p')}"
    elif dt.date() == (now + timedelta(days=1)).date():
        return f"Tomorrow at {dt.strftime('%I:%M %p')}"
    else:
        return dt.strftime('%b %d at %I:%M %p')
