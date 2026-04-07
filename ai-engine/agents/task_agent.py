"""
Task Agent for DecisionOS.
RULE-BASED agent - calculates urgency, importance, and priority scores.
NO LLM usage.
"""

from typing import Dict, Any
from datetime import datetime, timedelta

from ai_engine.config.defaults import (
    get_task_duration,
    get_priority_level,
    TASK_DURATIONS
)


def run_task_agent(
    extracted_data: Dict[str, Any],
    time_context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Analyze task and calculate scores using rule-based logic.
    
    Args:
        extracted_data: Output from planner agent (with defaults applied)
        time_context: Output from time resolver
        
    Returns:
        Dictionary with:
        - urgency_score (0-10)
        - importance_score (0-10)
        - priority (1-10)
        - estimated_duration (hours)
        - reasoning
    """
    # Calculate urgency based on deadline proximity
    urgency_score = _calculate_urgency(time_context)
    
    # Calculate importance based on task type and context
    importance_score = _calculate_importance(extracted_data)
    
    # Get or calculate estimated duration
    estimated_duration = extracted_data.get("estimated_duration")
    if not estimated_duration:
        task_type = extracted_data.get("task_type", "")
        estimated_duration = get_task_duration(task_type)
    
    # Calculate priority
    priority = get_priority_level(urgency_score, importance_score)
    
    # Generate reasoning
    reasoning = _generate_reasoning(
        urgency_score, 
        importance_score, 
        priority,
        time_context,
        extracted_data
    )
    
    return {
        "urgency_score": urgency_score,
        "importance_score": importance_score,
        "priority": priority,
        "estimated_duration": estimated_duration,
        "reasoning": reasoning
    }


def _calculate_urgency(time_context: Dict[str, Any]) -> float:
    """
    Calculate urgency score based on time constraints.
    
    Rules:
    - Deadline within 4 hours: 10
    - Deadline within 8 hours: 8
    - Deadline within 24 hours: 6
    - Deadline within 48 hours: 4
    - Deadline > 48 hours or none: 2
    
    Args:
        time_context: Dictionary with current_time and deadline
        
    Returns:
        Urgency score (0-10)
    """
    current_time = time_context.get("current_time", datetime.now())
    deadline = time_context.get("deadline")
    
    if deadline is None:
        return 2.0  # Low urgency if no deadline
    
    hours_until_deadline = (deadline - current_time).total_seconds() / 3600
    
    if hours_until_deadline <= 0:
        return 10.0  # Past deadline - maximum urgency
    elif hours_until_deadline <= 4:
        return 10.0
    elif hours_until_deadline <= 8:
        return 8.0
    elif hours_until_deadline <= 24:
        return 6.0
    elif hours_until_deadline <= 48:
        return 4.0
    else:
        return 2.0


def _calculate_importance(extracted_data: Dict[str, Any]) -> float:
    """
    Calculate importance score based on task type and context.
    
    Rules:
    - Exam/Test: 10 (academic critical)
    - Backend/API work: 8 (critical path)
    - Frontend work: 7
    - Gym/Exercise: 4 (personal wellness, can reschedule)
    - Testing: 6
    - Documentation: 4
    - Meeting: 5 (depends on context)
    
    Args:
        extracted_data: Dictionary with task_type and context
        
    Returns:
        Importance score (0-10)
    """
    task_type = (extracted_data.get("task_type") or "").lower()
    task_desc = (extracted_data.get("task_description") or "").lower()
    context = (extracted_data.get("context") or "").lower()
    constraints = extracted_data.get("constraints", [])
    event_type = (extracted_data.get("event_type") or "").lower()
    
    # Combined text for keyword search
    all_text = f"{task_type} {task_desc} {context} {event_type}"
    
    # Base importance from task type
    importance_map = {
        "exam": 10.0,
        "test": 9.0,
        "interview": 10.0,
        "deadline": 9.0,
        "presentation": 8.0,
        "deployment": 9.0,
        "backend": 8.0,
        "api": 8.0,
        "database": 8.0,
        "frontend": 7.0,
        "debugging": 7.0,
        "meeting": 5.0,
        "gym": 4.0,
        "exercise": 4.0,
        "workout": 4.0,
        "testing": 6.0,
        "review": 5.0,
        "documentation": 4.0,
        "planning": 5.0,
        "research": 4.0,
        "call": 5.0
    }
    
    # Find matching importance - check task_type first, then all_text
    base_importance = 5.0  # Default
    for key, value in importance_map.items():
        if key in task_type:
            base_importance = value
            break
        elif key in all_text:
            base_importance = value
            # Don't break - keep checking for more specific matches
    
    # Adjust for context
    if "client" in context or "customer" in context:
        base_importance = min(10.0, base_importance + 1.5)
    if "blocker" in context or "blocking" in context:
        base_importance = min(10.0, base_importance + 2.0)
    if "incomplete" in context or any("incomplete" in str(c).lower() for c in constraints):
        base_importance = min(10.0, base_importance + 1.0)
    
    return base_importance


def _generate_reasoning(
    urgency: float,
    importance: float,
    priority: int,
    time_context: Dict[str, Any],
    extracted_data: Dict[str, Any]
) -> str:
    """
    Generate human-readable reasoning for the scores.
    
    Args:
        urgency: Urgency score
        importance: Importance score
        priority: Priority level
        time_context: Time context dict
        extracted_data: Extracted data dict
        
    Returns:
        Reasoning string
    """
    parts = []
    
    # Urgency reasoning
    deadline = time_context.get("deadline")
    if deadline:
        hours_left = (deadline - time_context["current_time"]).total_seconds() / 3600
        if hours_left <= 24:
            parts.append(f"High urgency ({urgency}/10): deadline in {hours_left:.1f} hours")
        else:
            parts.append(f"Moderate urgency ({urgency}/10): deadline in {hours_left:.1f} hours")
    else:
        parts.append(f"Low urgency ({urgency}/10): no specific deadline")
    
    # Importance reasoning
    task_type = extracted_data.get("task_type", "task")
    if importance >= 8:
        parts.append(f"High importance ({importance}/10): {task_type} is critical")
    elif importance >= 6:
        parts.append(f"Moderate importance ({importance}/10): {task_type} needs attention")
    else:
        parts.append(f"Lower importance ({importance}/10): {task_type} can be flexible")
    
    # Priority conclusion
    if priority >= 8:
        parts.append(f"Priority {priority}/10: Requires immediate action")
    elif priority >= 5:
        parts.append(f"Priority {priority}/10: Should be addressed soon")
    else:
        parts.append(f"Priority {priority}/10: Can be scheduled flexibly")
    
    return ". ".join(parts)
