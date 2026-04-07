"""
Defaults layer for DecisionOS.
Provides deterministic system values - NO LLM usage.
Agents must NOT guess missing values; all missing values must be filled using defaults.
"""

from typing import Dict, Any

# ============================================================
# Task Duration Defaults (in hours)
# ============================================================

TASK_DURATIONS: Dict[str, float] = {
    # Development work
    "backend work": 5.0,
    "frontend work": 3.0,
    "backend development": 5.0,
    "frontend development": 3.0,
    "api development": 4.0,
    "database work": 3.0,
    "testing": 2.0,
    "debugging": 2.0,
    "code review": 1.5,
    "deployment": 1.0,
    "documentation": 1.5,
    
    # General work
    "meeting": 1.0,
    "presentation": 1.5,
    "planning": 1.0,
    "research": 2.0,
    "writing": 2.0,
    "design": 3.0,
    "review": 1.0,
    
    # Study/Academic
    "exam": 2.0,
    "exam prep": 2.0,
    "study": 2.0,
    
    # Default fallback
    "default": 2.0
}


# ============================================================
# Buffer Time Configuration
# ============================================================

BUFFER_TIME: float = 1.0  # hours - safety margin for scheduling
EVENT_BUFFER_MINUTES: int = 30  # minutes - buffer between events


# ============================================================
# Priority Classification (CRITICAL)
# ============================================================

HIGH_PRIORITY_EVENTS = {
    "exam", "examination", "test", "quiz",
    "deadline", "due date", "submission",
    "interview", "job interview",
    "presentation", "demo",
    "doctor", "medical", "hospital",
    "court", "legal",
    "flight", "travel"
}

LOW_PRIORITY_EVENTS = {
    "gym", "workout", "exercise", "fitness",
    "outing", "hangout", "party",
    "movie", "entertainment", "game",
    "shopping", "errands",
    "lunch", "dinner", "coffee",
    "casual meeting", "catch up"
}

MEDIUM_PRIORITY_EVENTS = {
    "meeting", "call", "sync",
    "class", "lecture", "seminar",
    "appointment"
}


# ============================================================
# Scoring Weights
# ============================================================

SCORING_WEIGHTS: Dict[str, float] = {
    "urgency": 0.4,
    "importance": 0.3,
    "feasibility": 0.3
}


# ============================================================
# Conflict Scoring Penalties (CRITICAL)
# ============================================================

CONFLICT_SCORE_PENALTIES = {
    # When conflict exists and task is high priority:
    "attend_low_priority_max": 25,  # Max score for attending low priority event
    "skip_low_priority_min": 85,    # Min score for skipping low priority event
    "reschedule_low_priority_min": 75,  # Min score for rescheduling
    
    # When conflict exists and task is low priority:
    "attend_high_priority_min": 80,  # Min score for attending high priority event
    "skip_high_priority_max": 30,    # Max score for skipping high priority event
}


# ============================================================
# Priority Mapping
# ============================================================

PRIORITY_THRESHOLDS: Dict[str, int] = {
    "critical": 10,
    "high": 8,
    "medium": 5,
    "low": 3
}


# ============================================================
# Default Meeting Duration (in hours)
# ============================================================

DEFAULT_MEETING_DURATION: float = 1.0


# ============================================================
# Urgency Score Threshold for Scenario Analysis
# ============================================================

URGENCY_THRESHOLD_FOR_SCENARIOS: int = 5  # Lowered from 6 to ensure scenarios run


# ============================================================
# Confidence Thresholds
# ============================================================

CONFIDENCE_THRESHOLDS: Dict[str, float] = {
    "high": 0.8,
    "medium": 0.6,
    "low": 0.4
}


# ============================================================
# Helper Functions
# ============================================================

def get_task_duration(task_type: str) -> float:
    """
    Get the estimated duration for a task type.
    Returns default if task type not found.
    
    Args:
        task_type: The type of task (e.g., 'backend work', 'meeting')
        
    Returns:
        Estimated duration in hours
    """
    if not task_type:
        return TASK_DURATIONS["default"]
    
    task_lower = task_type.lower().strip()
    
    # Exact match
    if task_lower in TASK_DURATIONS:
        return TASK_DURATIONS[task_lower]
    
    # Partial match
    for key, duration in TASK_DURATIONS.items():
        if key in task_lower or task_lower in key:
            return duration
    
    return TASK_DURATIONS["default"]


def classify_event_priority(event_name: str) -> str:
    """
    Classify an event as HIGH, MEDIUM, or LOW priority.
    
    Args:
        event_name: Name/type of the event
        
    Returns:
        "high", "medium", or "low"
    """
    if not event_name:
        return "medium"
    
    event_lower = event_name.lower().strip()
    
    # Check high priority
    for keyword in HIGH_PRIORITY_EVENTS:
        if keyword in event_lower:
            return "high"
    
    # Check low priority
    for keyword in LOW_PRIORITY_EVENTS:
        if keyword in event_lower:
            return "low"
    
    # Check medium priority
    for keyword in MEDIUM_PRIORITY_EVENTS:
        if keyword in event_lower:
            return "medium"
    
    return "medium"


def is_high_priority_task(task_type: str) -> bool:
    """Check if a task is high priority."""
    return classify_event_priority(task_type) == "high"


def is_low_priority_event(event_type: str) -> bool:
    """Check if an event is low priority."""
    return classify_event_priority(event_type) == "low"


def calculate_score(urgency: float, importance: float, feasibility: float) -> float:
    """
    Calculate weighted score using default weights.
    
    Args:
        urgency: Urgency score (0-10)
        importance: Importance score (0-10)
        feasibility: Feasibility score (0-10)
        
    Returns:
        Weighted score normalized to 0-100
    """
    score = (
        urgency * SCORING_WEIGHTS["urgency"] +
        importance * SCORING_WEIGHTS["importance"] +
        feasibility * SCORING_WEIGHTS["feasibility"]
    )
    # Normalize to 0-100
    return min(100, max(0, score * 10))


def get_priority_level(urgency: float, importance: float) -> int:
    """
    Calculate priority level based on urgency and importance.
    
    Args:
        urgency: Urgency score (0-10)
        importance: Importance score (0-10)
        
    Returns:
        Priority level (1-10)
    """
    # Simple average, capped at 10
    combined = (urgency * 0.6 + importance * 0.4)
    return min(10, max(1, round(combined)))


def apply_defaults(extracted_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply default values to extracted data where values are missing.
    
    Args:
        extracted_data: Dictionary from planner agent
        
    Returns:
        Dictionary with defaults applied
    """
    result = extracted_data.copy()
    
    # Apply default task duration if missing
    if not result.get("estimated_duration"):
        task_type = result.get("task_type", "")
        result["estimated_duration"] = get_task_duration(task_type)
    
    # Apply default meeting duration if meeting exists but duration not specified
    if result.get("meeting_raw") and not result.get("meeting_duration"):
        result["meeting_duration"] = DEFAULT_MEETING_DURATION
    
    # Apply buffer time
    result["buffer_time"] = BUFFER_TIME
    
    # Classify task priority
    task_type = result.get("task_type", "")
    result["task_priority_class"] = classify_event_priority(task_type)
    
    return result
