"""
Planner Agent for DecisionOS.
Extracts structured data from user input using LLM with retry logic.
Falls back to rule-based parser if LLM fails.
"""

import os
import re
import asyncio
import google.generativeai as genai
from typing import Dict, Any, Optional
from ai_engine.utils.helpers import safe_json

genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

MODEL = "gemini-2.0-flash"
TEMPERATURE = 0.2
MAX_RETRIES = 2

PLANNER_SYSTEM_PROMPT = """You are a data extraction agent. Your ONLY job is to extract structured information from the user's message.

RULES:
1. Extract ONLY what is explicitly stated - DO NOT assume or infer
2. If information is not present, use null
3. Output MUST be valid JSON only - no explanation, no markdown
4. Be literal - "meeting in 2 hours" means exactly that
5. Identify the PRIMARY task (most important thing to do) and any EVENTS/ACTIVITIES that might conflict

OUTPUT FORMAT (JSON only):
{
    "task_type": "<type of primary task: exam, work, study, project, etc.>",
    "task_description": "<description of what needs to be done>",
    "deadline_raw": "<raw deadline/time text for the task or null>",
    "event_raw": "<raw time text for any event/activity that conflicts: gym, meeting, etc. or null>",
    "event_type": "<type of event: gym, meeting, appointment, etc. or null>",
    "constraints": ["<list of any constraints or blockers mentioned>"],
    "context": "<any additional context or null>",
    "urgency_keywords": ["<urgent words found: exam, deadline, important, critical, etc.>"]
}

Examples:
Input: "I have exam in 2 hours and I have gym now"
Output: {"task_type": "exam", "task_description": "prepare for exam", "deadline_raw": "in 2 hours", "event_raw": "now", "event_type": "gym", "constraints": ["gym conflicts with exam prep"], "context": "need to prepare for exam", "urgency_keywords": ["exam"]}

Input: "Deadline tomorrow, backend incomplete, meeting in 2 hours"
Output: {"task_type": "backend work", "task_description": "complete backend work", "deadline_raw": "tomorrow", "event_raw": "in 2 hours", "event_type": "meeting", "constraints": ["backend incomplete"], "context": null, "urgency_keywords": ["deadline", "incomplete"]}
"""


def _rule_based_parser(message: str) -> Dict[str, Any]:
    """
    Rule-based fallback parser when LLM fails.
    Detects keywords and extracts time phrases.
    
    Args:
        message: User's input message
        
    Returns:
        Extracted data dictionary
    """
    message_lower = message.lower()
    
    # Detect task type from keywords
    task_type = None
    urgency_keywords = []
    
    # High urgency keywords
    urgent_patterns = {
        "exam": "exam",
        "test": "exam",
        "quiz": "exam",
        "deadline": "work",
        "due": "work",
        "urgent": "work",
        "important": "work",
        "critical": "work",
        "backend": "backend work",
        "frontend": "frontend work",
        "api": "api work",
        "project": "project",
        "presentation": "presentation",
        "interview": "interview",
        "study": "study",
        "assignment": "assignment"
    }
    
    for keyword, ttype in urgent_patterns.items():
        if keyword in message_lower:
            if task_type is None:
                task_type = ttype
            urgency_keywords.append(keyword)
    
    # Detect event type
    event_type = None
    event_patterns = ["gym", "meeting", "appointment", "call", "lunch", "dinner", "workout", "exercise", "class"]
    for pattern in event_patterns:
        if pattern in message_lower:
            event_type = pattern
            break
    
    # Extract time phrases
    deadline_raw = None
    event_raw = None
    
    # Deadline patterns
    deadline_matches = re.findall(
        r'(deadline\s+(?:in\s+)?\d+\s*(?:hours?|hrs?|minutes?|mins?)|'
        r'deadline\s+(?:tomorrow|today)|'
        r'due\s+(?:tomorrow|today)|'
        r'in\s+\d+\s*(?:hours?|hrs?)\s*(?:deadline|due)?|'
        r'tomorrow|'
        r'(?:exam|test|quiz)\s+in\s+\d+\s*(?:hours?|hrs?|minutes?|mins?))',
        message_lower
    )
    if deadline_matches:
        deadline_raw = deadline_matches[0]
    
    # Event time patterns
    event_matches = re.findall(
        r'((?:gym|meeting|appointment|call)\s+(?:in\s+)?\d+\s*(?:hours?|hrs?|minutes?|mins?)|'
        r'(?:gym|meeting|appointment|call)\s+(?:now|today|at\s+\d+)|'
        r'(?:gym|meeting|appointment|call)\s+(?:is\s+)?(?:now|starting)|'
        r'(?:have|has)\s+(?:gym|meeting|appointment|call)\s+now)',
        message_lower
    )
    if event_matches:
        event_raw = event_matches[0]
    elif event_type and "now" in message_lower:
        event_raw = "now"
    
    # Extract "in X hours" for deadline if exam/test mentioned
    if not deadline_raw and any(k in message_lower for k in ["exam", "test", "quiz"]):
        time_match = re.search(r'in\s+(\d+)\s*(?:hours?|hrs?|minutes?|mins?)', message_lower)
        if time_match:
            deadline_raw = time_match.group(0)
    
    # Build constraints
    constraints = []
    if event_type and task_type:
        constraints.append(f"{event_type} conflicts with {task_type}")
    if "incomplete" in message_lower:
        constraints.append("task incomplete")
    if "not done" in message_lower or "not finished" in message_lower:
        constraints.append("task not finished")
    
    return {
        "task_type": task_type or "general task",
        "task_description": message,
        "deadline_raw": deadline_raw,
        "event_raw": event_raw,
        "event_type": event_type,
        "constraints": constraints,
        "context": None,
        "urgency_keywords": urgency_keywords,
        "parse_error": False,
        "parser_used": "rule_based"
    }


async def run_planner_agent(message: str) -> Dict[str, Any]:
    """
    Extract structured data from user message.
    Uses LLM with retry logic, falls back to rule-based parser.
    
    Args:
        message: User's input message
        
    Returns:
        Dictionary with extracted data
    """
    last_error = None
    
    # Try LLM with retries

    model = genai.GenerativeModel(
        model_name=MODEL,
        generation_config={"temperature": TEMPERATURE}
    )

    for attempt in range(MAX_RETRIES):
        try:
            response = model.generate_content(
                f"{PLANNER_SYSTEM_PROMPT}\n\nUser Input:\n{message}"
            )

            content = response.text
            parsed = safe_json(content)
            
            if parsed is not None:
                # Ensure all expected keys exist
                result = {
                    "task_type": parsed.get("task_type"),
                    "task_description": parsed.get("task_description") or message,
                    "deadline_raw": parsed.get("deadline_raw"),
                    "event_raw": parsed.get("event_raw") or parsed.get("meeting_raw"),
                    "event_type": parsed.get("event_type") or ("meeting" if parsed.get("meeting_raw") else None),
                    "constraints": parsed.get("constraints", []),
                    "context": parsed.get("context"),
                    "urgency_keywords": parsed.get("urgency_keywords", []),
                    "parse_error": False,
                    "parser_used": "llm"
                }
                return result
            
            # JSON parse failed, retry
            last_error = "JSON parse failed"
            
        except Exception as e:
            last_error = str(e)
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(0.5)  # Brief delay before retry
    
    # LLM failed - use rule-based fallback
    result = _rule_based_parser(message)
    result["llm_error"] = last_error
    return result

def _clean_json(text: str) -> str:
    match = re.search(r'\{.*\}', text, re.DOTALL)
    return match.group(0) if match else text
