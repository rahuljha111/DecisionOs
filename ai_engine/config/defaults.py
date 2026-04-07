"""
Centralized defaults, constants, and classification helpers for DecisionOS.
All agents import from here — never define magic numbers inline.
"""

from typing import Optional

# ─────────────────────────────────────────────
# TIME CONSTANTS
# ─────────────────────────────────────────────

BUFFER_TIME = 0.5           # hours of buffer added on top of required time
EVENT_BUFFER_MINUTES = 30   # minimum gap (minutes) required between events
URGENCY_THRESHOLD_FOR_SCENARIOS = 6  # urgency score at or above which we run scenario agent

# ─────────────────────────────────────────────
# TASK DURATION ESTIMATES (hours)
# ─────────────────────────────────────────────

TASK_DURATIONS = {
    "exam":           3.0,
    "test":           2.0,
    "quiz":           1.0,
    "interview":      2.0,
    "presentation":   2.0,
    "deployment":     3.0,
    "backend":        4.0,
    "backend work":   4.0,
    "api":            3.0,
    "api work":       3.0,
    "frontend":       3.0,
    "frontend work":  3.0,
    "database":       3.0,
    "debugging":      2.0,
    "meeting":        1.0,
    "gym":            1.5,
    "exercise":       1.0,
    "workout":        1.5,
    "study":          2.0,
    "research":       2.0,
    "documentation":  2.0,
    "review":         1.0,
    "planning":       1.0,
    "project":        4.0,
    "assignment":     2.0,
    "call":           0.5,
    "lunch":          1.0,
    "dinner":         1.5,
}

DEFAULT_TASK_DURATION = 2.0   # fallback when task type unknown


# ─────────────────────────────────────────────
# SCORING WEIGHTS
# ─────────────────────────────────────────────

SCORING_WEIGHTS = {
    "urgency":    0.4,
    "importance": 0.35,
    "context":    0.25,
}

# Penalty/bonus applied per action when conflict is present
CONFLICT_SCORE_PENALTIES = {
    "skip":        +20,   # bonus for skipping low-priority event
    "attend":      -30,   # penalty for attending low-priority event under conflict
    "reschedule":  +10,   # modest bonus
}


# ─────────────────────────────────────────────
# PRIORITY CLASSIFICATION
# ─────────────────────────────────────────────

HIGH_PRIORITY_TASKS = {
    "exam", "test", "quiz", "interview", "deadline", "deployment",
    "backend", "backend work", "api", "api work", "presentation", "project"
}

LOW_PRIORITY_EVENTS = {
    "gym", "exercise", "workout", "lunch", "dinner", "call",
    "social", "break", "walk", "nap"
}


def classify_event_priority(event_type: str) -> str:
    """
    Return 'high', 'medium', or 'low' for a given event/task type string.

    Args:
        event_type: String describing the task or event type

    Returns:
        Priority string: 'high' | 'medium' | 'low'
    """
    if not event_type:
        return "medium"

    lower = event_type.lower().strip()

    for key in HIGH_PRIORITY_TASKS:
        if key in lower:
            return "high"

    for key in LOW_PRIORITY_EVENTS:
        if key in lower:
            return "low"

    return "medium"


def is_high_priority_task(task_type: str) -> bool:
    """Return True if the task type is considered high priority."""
    return classify_event_priority(task_type) == "high"


def is_low_priority_event(event_type: str) -> bool:
    """Return True if the event type is considered low priority."""
    return classify_event_priority(event_type) == "low"


# ─────────────────────────────────────────────
# DURATION HELPERS
# ─────────────────────────────────────────────

def get_task_duration(task_type: str) -> float:
    """
    Return estimated task duration in hours for a given task type.

    Args:
        task_type: Type of task (e.g., 'exam', 'gym', 'backend')

    Returns:
        Duration in hours
    """
    if not task_type:
        return DEFAULT_TASK_DURATION

    lower = task_type.lower().strip()

    # Exact match first
    if lower in TASK_DURATIONS:
        return TASK_DURATIONS[lower]

    # Partial match
    for key, duration in TASK_DURATIONS.items():
        if key in lower:
            return duration

    return DEFAULT_TASK_DURATION


# ─────────────────────────────────────────────
# PRIORITY LEVEL CALCULATOR
# ─────────────────────────────────────────────

def get_priority_level(urgency_score: float, importance_score: float) -> int:
    """
    Combine urgency and importance into a single priority level (1-10).

    Args:
        urgency_score: 0-10 urgency score from task agent
        importance_score: 0-10 importance score from task agent

    Returns:
        Priority integer from 1 to 10
    """
    w = SCORING_WEIGHTS
    combined = (urgency_score * w["urgency"]) + (importance_score * w["importance"])
    # Scale to 1-10
    priority = round(combined)
    return max(1, min(10, priority))


# ─────────────────────────────────────────────
# DEFAULTS APPLIER
# ─────────────────────────────────────────────

def apply_defaults(planner_output: dict) -> dict:
    """
    Fill missing fields in planner output with safe defaults.
    Never overwrites values that were explicitly extracted.

    Args:
        planner_output: Output dictionary from planner agent

    Returns:
        Dictionary with guaranteed non-None values for all required keys
    """
    result = dict(planner_output)  # shallow copy

    # Task type default
    if not result.get("task_type"):
        result["task_type"] = "general task"

    # Task description default
    if not result.get("task_description"):
        result["task_description"] = result.get("task_type", "task")

    # Estimated duration default (derived from task type)
    if not result.get("estimated_duration"):
        result["estimated_duration"] = get_task_duration(result["task_type"])

    # Buffer time default
    if not result.get("buffer_time"):
        result["buffer_time"] = BUFFER_TIME

    # Constraints default
    if not result.get("constraints"):
        result["constraints"] = []

    # Urgency keywords default
    if not result.get("urgency_keywords"):
        result["urgency_keywords"] = []

    # Event type default (None is fine — means no conflicting event)
    if "event_type" not in result:
        result["event_type"] = None

    return result