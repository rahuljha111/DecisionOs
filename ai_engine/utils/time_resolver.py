"""
Time Resolver for DecisionOS.
Converts natural language time expressions into structured datetime context.
Rule-based only — no LLM usage.

Handles patterns like:
  - "in 2 hours"
  - "tomorrow"
  - "at 3pm"
  - "now"
  - "tonight"
  - "in 30 minutes"
"""

import re
from datetime import datetime, timedelta
from typing import Dict, Any, Optional


# ─────────────────────────────────────────────
# PUBLIC ENTRY POINT
# ─────────────────────────────────────────────

def resolve_time_context(message: str) -> Dict[str, Any]:
    """
    Parse a user message and extract a structured time context.

    Returns a dict with:
        current_time  : datetime  – always set to now()
        deadline      : datetime | None – when the task must be done
        event_start   : datetime | None – when a conflicting event begins
        event_end     : datetime | None – when the conflicting event ends
        event_duration: float           – event length in hours (default 1.0)
        event_type    : str | None      – detected event type keyword
        hours_until_deadline : float | None
    """
    now = datetime.now()
    lower = message.lower()

    deadline = _extract_deadline(lower, now)
    event_start, event_duration, event_type = _extract_event_time(lower, now)
    event_end = event_start + timedelta(hours=event_duration) if event_start else None

    hours_until_deadline = None
    if deadline:
        hours_until_deadline = max(0.0, (deadline - now).total_seconds() / 3600)

    return {
        "current_time": now,
        "deadline": deadline,
        "event_start": event_start,
        "event_end": event_end,
        "event_duration": event_duration,
        "event_type": event_type,
        "hours_until_deadline": hours_until_deadline,
        # Alias keys used by calendar agent
        "meeting_start": event_start,
        "meeting_end": event_end,
    }


# ─────────────────────────────────────────────
# DEADLINE EXTRACTION
# ─────────────────────────────────────────────

def _extract_deadline(text: str, now: datetime) -> Optional[datetime]:
    """Extract deadline datetime from text."""

    # "in X hours" / "in X hrs"
    m = re.search(r'(?:deadline\s+)?in\s+(\d+(?:\.\d+)?)\s*(?:hours?|hrs?)', text)
    if m:
        return now + timedelta(hours=float(m.group(1)))

    # "in X minutes" / "in X mins"
    m = re.search(r'(?:deadline\s+)?in\s+(\d+)\s*(?:minutes?|mins?)', text)
    if m:
        return now + timedelta(minutes=int(m.group(1)))

    # "tomorrow" – set to 9am tomorrow as a reasonable deadline
    if re.search(r'\btomorrow\b', text):
        tomorrow = now + timedelta(days=1)
        return tomorrow.replace(hour=9, minute=0, second=0, microsecond=0)

    # "tonight" – set to 11pm today
    if re.search(r'\btonight\b', text):
        return now.replace(hour=23, minute=0, second=0, microsecond=0)

    # "at Xpm" / "at X:XXpm"
    m = re.search(r'\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b', text)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2)) if m.group(2) else 0
        if m.group(3) == "pm" and hour != 12:
            hour += 12
        elif m.group(3) == "am" and hour == 12:
            hour = 0
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate < now:
            candidate += timedelta(days=1)
        return candidate

    # "by X" shorthand (e.g. "by 5pm")
    m = re.search(r'\bby\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b', text)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2)) if m.group(2) else 0
        if m.group(3) == "pm" and hour != 12:
            hour += 12
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate < now:
            candidate += timedelta(days=1)
        return candidate

    return None


# ─────────────────────────────────────────────
# EVENT TIME EXTRACTION
# ─────────────────────────────────────────────

_EVENT_KEYWORDS = [
    "gym", "meeting", "appointment", "call", "lunch", "dinner",
    "workout", "exercise", "class", "standup", "interview", "session"
]

_EVENT_DURATIONS = {
    "gym": 1.5,
    "workout": 1.5,
    "exercise": 1.0,
    "lunch": 1.0,
    "dinner": 1.5,
    "meeting": 1.0,
    "standup": 0.5,
    "call": 0.5,
    "appointment": 1.0,
    "class": 1.5,
    "interview": 1.5,
    "session": 1.0,
}


def _extract_event_time(
    text: str,
    now: datetime
) -> tuple:
    """
    Detect a conflicting event and its start time.

    Returns (event_start, duration_hours, event_type)
    """
    detected_event = None
    for kw in _EVENT_KEYWORDS:
        if kw in text:
            detected_event = kw
            break

    if not detected_event:
        return None, 1.0, None

    duration = _EVENT_DURATIONS.get(detected_event, 1.0)

    # "now" — event is happening right now
    pattern_now = rf'\b{detected_event}\b.*?\bnow\b|\bnow\b.*?\b{detected_event}\b'
    if re.search(pattern_now, text):
        return now, duration, detected_event

    # "in X minutes"
    m = re.search(
        rf'\b{detected_event}\b.*?in\s+(\d+)\s*(?:minutes?|mins?)|'
        rf'in\s+(\d+)\s*(?:minutes?|mins?).*?\b{detected_event}\b',
        text
    )
    if m:
        mins = int(m.group(1) or m.group(2))
        return now + timedelta(minutes=mins), duration, detected_event

    # "in X hours"
    m = re.search(
        rf'\b{detected_event}\b.*?in\s+(\d+(?:\.\d+)?)\s*(?:hours?|hrs?)|'
        rf'in\s+(\d+(?:\.\d+)?)\s*(?:hours?|hrs?).*?\b{detected_event}\b',
        text
    )
    if m:
        hrs = float(m.group(1) or m.group(2))
        return now + timedelta(hours=hrs), duration, detected_event

    # "at Xpm"
    m = re.search(
        rf'\b{detected_event}\b.*?at\s+(\d{{1,2}})(?::(\d{{2}}))?\s*(am|pm)|'
        rf'at\s+(\d{{1,2}})(?::(\d{{2}}))?\s*(am|pm).*?\b{detected_event}\b',
        text
    )
    if m:
        groups = m.groups()
        hour = int(groups[0] or groups[3])
        minute = int(groups[1] or groups[4] or 0)
        ampm = groups[2] or groups[5]
        if ampm == "pm" and hour != 12:
            hour += 12
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate < now:
            candidate += timedelta(days=1)
        return candidate, duration, detected_event

    # Event mentioned but no time → assume it starts now
    return now, duration, detected_event