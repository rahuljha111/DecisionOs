"""
Helper utilities for DecisionOS.
"""

import json
import re
from datetime import datetime
from typing import Any, Dict, Optional


class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles datetime objects."""
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


def safe_json(text: str) -> Optional[Dict[str, Any]]:
    """
    Safely parse JSON from LLM output.
    Handles common issues like markdown code blocks, trailing commas, etc.
    
    Args:
        text: Raw text that may contain JSON
        
    Returns:
        Parsed dictionary or None if parsing fails
    """
    if not text:
        return None
    
    # Remove markdown code blocks
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    
    # Try to find JSON object boundaries
    start_idx = text.find("{")
    end_idx = text.rfind("}") + 1
    
    if start_idx == -1 or end_idx == 0:
        # Try to find JSON array
        start_idx = text.find("[")
        end_idx = text.rfind("]") + 1
    
    if start_idx == -1 or end_idx == 0:
        return None
    
    json_str = text[start_idx:end_idx]
    
    # Fix common JSON issues
    # Remove trailing commas before } or ]
    json_str = re.sub(r',\s*([}\]])', r'\1', json_str)
    
    # Fix single quotes to double quotes (carefully)
    # Only do this if there are no double quotes
    if '"' not in json_str and "'" in json_str:
        json_str = json_str.replace("'", '"')
    
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        # Try a more aggressive cleanup
        try:
            # Remove comments
            json_str = re.sub(r'//.*?\n', '\n', json_str)
            json_str = re.sub(r'/\*.*?\*/', '', json_str, flags=re.DOTALL)
            return json.loads(json_str)
        except json.JSONDecodeError:
            return None


def format_sse_event(event: str, data: Dict[str, Any]) -> str:
    """
    Format data as a Server-Sent Event.
    Handles datetime objects automatically.
    
    Args:
        event: Event name
        data: Data dictionary to serialize
        
    Returns:
        Formatted SSE string
    """
    json_data = json.dumps(data, cls=DateTimeEncoder)
    return f"event: {event}\ndata: {json_data}\n\n"


def clamp(value: float, min_val: float, max_val: float) -> float:
    """
    Clamp a value to a range.
    
    Args:
        value: Value to clamp
        min_val: Minimum allowed value
        max_val: Maximum allowed value
        
    Returns:
        Clamped value
    """
    return max(min_val, min(max_val, value))


def extract_number(text: str) -> Optional[float]:
    """
    Extract first number from text.
    
    Args:
        text: Text containing a number
        
    Returns:
        Extracted number or None
    """
    if not text:
        return None
    
    match = re.search(r'[\d.]+', text)
    if match:
        try:
            return float(match.group())
        except ValueError:
            return None
    return None


def normalize_score(score: float, min_in: float = 0, max_in: float = 10, 
                    min_out: float = 0, max_out: float = 100) -> float:
    """
    Normalize a score from one range to another.
    
    Args:
        score: Input score
        min_in: Input minimum
        max_in: Input maximum
        min_out: Output minimum
        max_out: Output maximum
        
    Returns:
        Normalized score
    """
    if max_in == min_in:
        return min_out
    
    normalized = (score - min_in) / (max_in - min_in)
    return min_out + normalized * (max_out - min_out)
