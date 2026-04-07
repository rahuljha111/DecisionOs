"""
Decision Engine for DecisionOS.
STRICTLY uses scenario scores to make decisions.

RULES:
- MUST select highest scoring scenario
- NO fallback decision logic beyond scores
- If scores are identical → ERROR
- Enforces priority constraints
"""

from typing import Dict, Any


class DecisionEngineError(Exception):
    pass


def _normalize_action(action: str) -> str:
    """Normalize action into core type."""
    if not action:
        return ""

    action = action.lower().strip()

    if "skip" in action:
        return "skip"
    if "attend" in action:
        return "attend"
    if "reschedule" in action:
        return "reschedule"

    return action


async def run_decision_engine(
    extracted_data: Dict[str, Any],
    task_analysis: Dict[str, Any],
    calendar_result: Dict[str, Any],
    scenario_analysis: Dict[str, Any],
    time_context: Dict[str, Any]
) -> Dict[str, Any]:

    options = scenario_analysis.get("options", [])

    # ✅ MUST have scenarios
    if not options:
        raise DecisionEngineError("No scenarios provided")

    # ✅ Scores must be different
    scores = [opt.get("score", 0) for opt in options]
    if len(set(scores)) == 1:
        raise DecisionEngineError(f"All scenario scores identical: {scores}")

    # ✅ Sort by score
    options = sorted(options, key=lambda x: x.get("score", 0), reverse=True)
    best_option = options[0]

    best_action = best_option.get("action", "")
    best_score = best_option.get("score", 0)

    # ============================================================
    # PRIORITY VALIDATION (CRITICAL)
    # ============================================================

    has_conflict = calendar_result.get("has_conflict", False)
    task_priority = calendar_result.get("task_priority", "medium")
    event_priority = calendar_result.get("event_priority", "medium")

    normalized_action = _normalize_action(best_action)

    # ❗ Cannot attend low priority event if task is high priority
    if has_conflict and task_priority == "high" and event_priority == "low":
        if normalized_action == "attend":
            for opt in options:
                if _normalize_action(opt.get("action")) == "skip":
                    best_option = opt
                    best_action = opt.get("action")
                    best_score = opt.get("score")
                    break

    # ============================================================
    # FINAL DECISION OUTPUT
    # ============================================================

    confidence = min(95, max(60, best_score))

    return {
        "action": best_action,
        "decision_text": best_action.replace("_", " ").capitalize(),
        "confidence": confidence,
        "reasoning": f"Selected '{best_action}' because it has the highest score ({best_score}/100).",
        "selected_score": best_score,
        "alternatives": [
            {
                "action": opt.get("action"),
                "score": opt.get("score")
            }
            for opt in options[1:]
        ],
        "next_steps": _generate_next_steps(best_action, extracted_data),
        "mcp_actions": _generate_mcp_actions(best_option)
    }


# ============================================================
# DIRECT DECISION (NO SCENARIOS)
# ============================================================

async def make_direct_decision(
    extracted_data: Dict[str, Any],
    task_analysis: Dict[str, Any],
    calendar_result: Dict[str, Any],
    time_context: Dict[str, Any]
) -> Dict[str, Any]:

    urgency = task_analysis.get("urgency_score", 5)
    available_time = calendar_result.get("available_time", 0)
    required_time = calendar_result.get("required_time", 1)

    if available_time >= required_time:
        action = "proceed"
        confidence = 85 if urgency >= 6 else 75
    else:
        action = "delay"
        confidence = 60

    return {
        "action": action,
        "decision_text": action.capitalize(),
        "confidence": confidence,
        "reasoning": "Based on available time and urgency",
        "next_steps": _generate_next_steps(action, extracted_data),
        "mcp_actions": []
    }


# ============================================================
# HELPERS
# ============================================================

def _generate_next_steps(action: str, extracted_data: Dict[str, Any]) -> list:
    task = extracted_data.get("task_description", "task")

    if "skip" in action:
        return [
            f"Focus fully on {task}",
            "Avoid distractions",
            "Complete high priority work"
        ]

    elif "attend" in action:
        return [
            "Attend the event",
            f"Resume {task} later",
            "Manage time efficiently"
        ]

    elif "reschedule" in action:
        return [
            "Reschedule the event",
            f"Focus on {task} now",
            "Follow up later"
        ]

    elif action == "proceed":
        return [
            f"Start working on {task}",
            "Use available time efficiently"
        ]

    elif action == "delay":
        return [
            "Re-evaluate schedule",
            "Allocate more time later"
        ]

    return ["Take appropriate action"]


def _generate_mcp_actions(best_option: Dict[str, Any]) -> list:
    action = best_option.get("action", "")

    if "reschedule" in action:
        return [{
            "tool": "calendar_reschedule",
            "event_id": best_option.get("event_id"),
            "suggested_time": best_option.get("suggested_time")
        }]

    if "skip" in action:
        return [{
            "tool": "calendar_cancel",
            "event_id": best_option.get("event_id")
        }]

    return []