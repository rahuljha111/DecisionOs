"""
Shared utility helpers for DecisionOS.
Imported by planner agent, orchestrator, and scenario agent.
"""

import re
import json
from datetime import datetime
from typing import Any, Dict, Optional


# ─────────────────────────────────────────────
# JSON HELPERS
# ─────────────────────────────────────────────

class DateTimeEncoder(json.JSONEncoder):
    """JSON encoder that converts datetime objects to ISO strings."""

    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


def safe_json(text: str) -> Optional[Dict[str, Any]]:
    """
    Safely parse JSON from a string, stripping markdown fences and
    extracting the first {...} block if necessary.

    Args:
        text: Raw string that may contain JSON (possibly wrapped in markdown)

    Returns:
        Parsed dict, or None if parsing fails
    """
    if not text:
        return None

    # Strip markdown code fences  ```json ... ``` or ``` ... ```
    cleaned = re.sub(r"```(?:json)?", "", text).strip()

    # Try direct parse first
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Try to find first {...} block
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return None


# ─────────────────────────────────────────────
# SSE STREAMING HELPER
# ─────────────────────────────────────────────

def format_sse_event(event_type: str, data: Any) -> str:
    """
    Format a Server-Sent Event string.

    Args:
        event_type: SSE event name (e.g., 'agent_start', 'complete')
        data: Data to serialize as JSON

    Returns:
        SSE formatted string ready to yield from a FastAPI StreamingResponse
    """
    payload = json.dumps(data, cls=DateTimeEncoder)
    return f"event: {event_type}\ndata: {payload}\n\n"