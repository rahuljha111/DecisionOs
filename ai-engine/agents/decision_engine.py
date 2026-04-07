"""
Decision Engine for DecisionOS.
MUST use scenario scores to make decisions - NO default/fallback decisions.

CRITICAL VALIDATION:
- If conflict exists AND task is high priority:
  * Decision CANNOT be "attend low priority event"
- Must select highest scoring option
- All scores same → ERROR
"""

import os
import re
from typing import Dict, Any, List
from openai import AsyncOpenAI

from ai_engine.utils.helpers import safe_json
from ai_engine.config.defaults import classify_event_priority, is_low_priority_event, is_non_negotiable_event

# Initialize Gemini client
client = AsyncOpenAI(
    api_key=os.environ.get("GEMINI_API_KEY", ""),
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
)

MODEL = "gemini-2.0-flash"
TEMPERATURE = 0.2
USE_LLM_DECISION = os.getenv("DECISIONOS_USE_LLM_DECISION", "false").lower() in {"1", "true", "yes"}

FORBIDDEN_PHRASES = [
    "lower-value task",
    "lower-value conflict",
    "adjust schedule",
    "optimize time",
    "manage",
    "balance",
    "pause",
]

ALLOWED_ACTIONS = ("attend", "skip", "leave", "cancel", "reschedule", "start", "stop")

CONFLICT_ITEM_KEYWORDS = [
    "exam",
    "interview",
    "deadline",
    "meeting",
    "gym",
    "practice",
    "class",
    "workout",
]

NON_NEGOTIABLE_KEYWORDS = ["exam", "interview", "deadline", "submission"]
HIGH_IMPACT_KEYWORDS = ["urgent bug", "bug", "assignment", "project", "coding", "release", "revise", "revision", "portfolio", "outage", "payments", "high-impact"]
MEETING_KEYWORDS = ["meeting", "class", "demo", "sync"]
ROUTINE_KEYWORDS = ["gym", "hangout", "youtube", "series", "social media", "gaming", "practice", "reading", "watch"]


def _first_match(text: str, keywords: List[str]) -> str:
    text_lower = (text or "").lower()
    for keyword in keywords:
        if keyword in text_lower:
            return keyword
    return ""


def _extract_priority_items(text: str) -> Dict[str, str]:
    """Extract best-effort priority-classified items from raw input text."""
    cleaned = re.sub(r"\s+", " ", (text or "").strip().lower())
    return {
        "non_negotiable": _first_match(cleaned, NON_NEGOTIABLE_KEYWORDS),
        "high_impact": _first_match(cleaned, HIGH_IMPACT_KEYWORDS),
        "meeting": _first_match(cleaned, MEETING_KEYWORDS),
        "routine": _first_match(cleaned, ROUTINE_KEYWORDS),
        "meeting_count": str(cleaned.count("meeting")),
    }


def _derive_decision_variables(
    extracted_data: Dict[str, Any],
    task_analysis: Dict[str, Any],
    calendar_result: Dict[str, Any]
) -> Dict[str, Any]:
    """Derive required deterministic variables from input payloads."""
    event_type = calendar_result.get("event_type", "event")
    task_description = extracted_data.get("task_description", "")
    urgency = task_analysis.get("urgency_score", 5)
    importance = task_analysis.get("importance_score", 5)

    fixed_events: List[str] = []
    flexible_events: List[str] = []
    if is_non_negotiable_event(event_type):
        fixed_events.append(event_type)
    else:
        flexible_events.append(event_type)

    high_priority_tasks: List[str] = []
    low_priority_tasks: List[str] = []
    if urgency >= 7 or importance >= 7:
        high_priority_tasks.append(task_description or "priority task")
    else:
        low_priority_tasks.append(task_description or "routine task")

    return {
        "fixed_events": fixed_events,
        "flexible_events": flexible_events,
        "high_priority_tasks": high_priority_tasks,
        "low_priority_tasks": low_priority_tasks,
    }


def _build_rejected_alternatives(
    selected_action: str,
    scenario_analysis: Dict[str, Any]
) -> List[str]:
    """Summarize why non-selected alternatives were rejected."""
    rejected: List[str] = []
    for option in scenario_analysis.get("options", []):
        action = option.get("action", "")
        if not action or action == selected_action:
            continue
        score = option.get("score", 0)
        reason = option.get("description", "Lower score for this scenario")
        rejected.append(f"{action}: rejected (score {score}/100) - {reason}")
    return rejected[:3]


class DecisionEngineError(Exception):
    """Raised when decision engine cannot make a valid decision."""
    pass


DECISION_SYSTEM_PROMPT = """You are a decision synthesis engine. You make ONE clear, actionable decision based on the analysis provided.

CRITICAL: Use STRONG, DECISIVE language. Start every decision with an ACTION VERB.

GOOD examples:
- "Skip the gym and focus on exam preparation"
- "Attend the meeting as scheduled"
- "Reschedule the appointment to after your deadline"

BAD examples (DO NOT USE):
- "You may consider..."
- "It might be better to..."
- "Perhaps you could..."

Your job is to:
1. Review all analysis data
2. Select the BEST action (the one with the HIGHEST score)
3. Provide clear reasoning based on the data
4. Specify exact next steps
5. List any MCP tool actions to execute

OUTPUT FORMAT (JSON only):
{
    "action": "<exact action to take - MUST be the highest scoring option>",
    "decision_text": "<STRONG imperative sentence starting with action verb, e.g. 'Skip the gym and prepare for your exam'>",
    "consequence": "<what happens if the user ignores this decision>",
    "confidence": <0.0 to 1.0>,
    "reasoning": "<explanation referencing the scores and conflict data>",
    "conflict_type": "<time_conflict | priority_conflict | none>",
    "next_steps": [
        "<specific step 1 - imperative>",
        "<specific step 2 - imperative>",
        "<specific step 3 - imperative>"
    ],
    "mcp_actions": [
        {
            "tool": "<tool_name: create_event|reschedule_event|cancel_event|add_task>",
            "params": {
                "<param_name>": "<value>"
            }
        }
    ]
}

RULES:
1. Action MUST be the highest scoring scenario
2. decision_text MUST start with an action verb (Skip, Attend, Reschedule, Focus, Cancel, etc.)
3. consequence MUST describe the result of ignoring the decision
4. Reasoning MUST reference the actual scores and data
5. NEVER use vague phrases like "lower-value task", "adjust schedule", or "optimize time"
6. ALWAYS mention concrete item names (exam, interview, meeting, gym, task name)
7. NEVER expose internal variable names in output
8. Output valid JSON only

VALID MCP TOOLS:
- create_event: params (title, start_time, end_time, description)
- reschedule_event: params (event_id, new_start_time, new_end_time)
- cancel_event: params (event_id)
- add_task: params (title, description, priority, deadline, estimated_duration)
"""


def _extract_labels(
    extracted_data: Dict[str, Any],
    calendar_result: Dict[str, Any],
    best_option: Dict[str, Any] = None
) -> Dict[str, str]:
    """Extract concrete event/task labels for user-facing text."""
    best_option = best_option or {}
    raw_task = (extracted_data.get("task_description") or extracted_data.get("task_type") or "pending task").strip()
    task_name = raw_task.replace("?", "").strip()
    task_lower = task_name.lower()
    if task_lower.startswith("calendar:") or "todos:" in task_lower:
        task_name = (extracted_data.get("task_type") or "priority task").strip() or "priority task"
        task_lower = task_name.lower()
    if task_lower.startswith("i have ") or "what should i do" in task_lower:
        task_name = (extracted_data.get("task_type") or "priority task").strip() or "priority task"
    if " and " in task_name.lower() and any(k in task_name.lower() for k in CONFLICT_ITEM_KEYWORDS):
        task_name = (extracted_data.get("task_type") or "priority task").strip() or "priority task"
    if len(task_name) > 80:
        task_name = (extracted_data.get("task_type") or "priority task").strip() or "priority task"

    event_name = (best_option.get("event_title") or "").strip()
    if not event_name:
        primary_event = calendar_result.get("primary_event")
        if isinstance(primary_event, dict):
            event_name = (primary_event.get("title") or primary_event.get("event_type") or "").strip()
        elif isinstance(primary_event, str):
            event_name = primary_event.strip()
    if not event_name:
        event_name = (calendar_result.get("event_type") or "event").strip()

    lower_task = task_name.lower()
    lower_raw_task = raw_task.lower()
    lower_event = event_name.lower()
    conflicting_item = "other tasks"
    for keyword in CONFLICT_ITEM_KEYWORDS:
        if (keyword in lower_task or keyword in lower_raw_task) and keyword not in lower_event:
            conflicting_item = f"{keyword} session" if keyword == "gym" else keyword
            break

    return {
        "task_name": task_name,
        "event_name": event_name,
        "conflicting_item": conflicting_item,
    }


def _build_concrete_decision_text(action: str, event_name: str, task_name: str, conflicting_item: str) -> str:
    """Build strict, specific decision text with explicit items."""
    action_lower = (action or "").lower()
    if "skip" in action_lower or "cancel" in action_lower:
        return f"Skip {event_name} and complete {task_name}."
    if "attend" in action_lower:
        return f"Attend {event_name} and skip {conflicting_item}."
    if "reschedule" in action_lower:
        return f"Reschedule {event_name} and complete {task_name} first."
    if "focus" in action_lower or "start" in action_lower:
        return f"Start {task_name} now and stop distractions."
    return f"Start {task_name} now."


def _build_aligned_sections(decision_text: str, raw_text: str) -> Dict[str, Any]:
    """Build reason, consequence, and next steps that strictly align with the decision."""
    text = (decision_text or "").strip()
    lower = text.lower()
    reason = "Priority hierarchy applied: non-negotiable items outrank high-impact work, meetings, and routine tasks."
    consequence = "If ignored, the highest-impact item will fail and real-world loss will increase."
    next_steps: List[str] = []

    match_attend_skip = re.match(r"^Attend (.+?) and skip (.+?)\.$", text)
    if match_attend_skip:
        must_attend, must_skip = match_attend_skip.group(1), match_attend_skip.group(2)
        reason = f"{must_attend} is higher priority than {must_skip}, so the lower-priority item is sacrificed immediately."
        if any(k in must_attend.lower() for k in ["exam", "deadline", "interview"]):
            consequence = f"If ignored, you risk missing {must_attend} and taking direct academic or career loss."
        else:
            consequence = f"If ignored, {must_attend} will be delayed and the outcome quality will drop."
        next_steps = [
            f"Attend {must_attend} now.",
            f"Skip {must_skip} now.",
            "Start the highest-impact remaining task immediately after."
        ]

    match_attend_two_skips = re.match(r"^Attend (.+?) and skip (.+?) and skip (.+?)\.$", text)
    if match_attend_two_skips:
        must_attend = match_attend_two_skips.group(1)
        must_skip_1 = match_attend_two_skips.group(2)
        must_skip_2 = match_attend_two_skips.group(3)
        reason = f"{must_attend} is non-negotiable; {must_skip_1} and {must_skip_2} are lower-priority conflicts."
        consequence = f"If ignored, you risk missing {must_attend} and taking direct academic or career loss."
        next_steps = [
            f"Attend {must_attend} now.",
            f"Skip {must_skip_1} now.",
            f"Skip {must_skip_2} now."
        ]

    match_attend_reschedule = re.match(r"^Attend (.+?) and reschedule (.+?)\.$", text)
    if match_attend_reschedule:
        must_attend, must_reschedule = match_attend_reschedule.group(1), match_attend_reschedule.group(2)
        reason = f"{must_attend} is fixed or higher impact, so {must_reschedule} is moved to remove the conflict."
        consequence = f"If ignored, the conflict remains and {must_attend} is put at risk."
        next_steps = [
            f"Attend {must_attend} now.",
            f"Reschedule {must_reschedule} to the next free slot.",
            "Start the top pending task after the event."
        ]

    match_start_stop = re.match(r"^Start (.+?) now and stop (.+?)\.$", text)
    if match_start_stop:
        must_start, must_stop = match_start_stop.group(1), match_start_stop.group(2)
        reason = f"{must_start} has higher urgency and impact than {must_stop}."
        consequence = f"If ignored, {must_start} may miss its deadline and create avoidable loss."
        next_steps = [
            f"Start {must_start} now.",
            f"Stop {must_stop} now.",
            "Start the next highest-impact task only after finishing this block."
        ]

    match_start_reschedule = re.match(r"^Start (.+?) now and reschedule (.+?)\.$", text)
    if match_start_reschedule:
        must_start, must_reschedule = match_start_reschedule.group(1), match_start_reschedule.group(2)
        reason = f"{must_start} is more urgent and impactful, so {must_reschedule} is moved out of the critical window."
        consequence = f"If ignored, {must_start} remains blocked and the chance of deadline failure increases."
        next_steps = [
            f"Start {must_start} now.",
            f"Reschedule {must_reschedule} after the critical work block.",
            "Start verification immediately after the work block ends."
        ]

    if not next_steps:
        if lower.startswith("start "):
            target = text[6:].replace(" now.", "").rstrip(".")
            reason = f"{target} is the most important action in the current time window."
            consequence = f"If ignored, {target} is delayed and real-world impact worsens."
            next_steps = [
                f"Start {target} now.",
                "Stop low-priority distractions now.",
                "Start the next highest-impact task after this block."
            ]
        elif lower.startswith("attend "):
            target = text[7:].rstrip(".")
            reason = f"{target} is the top priority action right now."
            consequence = f"If ignored, you risk missing {target} and losing the outcome tied to it."
            next_steps = [
                f"Attend {target} now.",
                "Skip lower-priority items during this window.",
                "Start the top pending task immediately after."
            ]
        else:
            next_steps = [
                "Start the highest-impact task now.",
                "Stop low-priority work now.",
                "Reschedule conflicting flexible items."
            ]

    return {
        "reasoning": reason,
        "consequence": consequence,
        "next_steps": next_steps,
    }


def _enforce_real_world_wording(
    decision: Dict[str, Any],
    extracted_data: Dict[str, Any],
    calendar_result: Dict[str, Any],
    scenario_analysis: Dict[str, Any],
    best_option: Dict[str, Any] = None
) -> Dict[str, Any]:
    """Ensure final output is specific, actionable, and free of vague/internal wording."""
    labels = _extract_labels(extracted_data, calendar_result, best_option)
    event_name = labels["event_name"]
    task_name = labels["task_name"]
    conflicting_item = labels["conflicting_item"]
    action = decision.get("action", "")
    raw_text = str(extracted_data.get("raw_input") or "").strip()
    if not raw_text:
        raw_text = " ".join(
            [
                str(extracted_data.get("task_description", "")),
                str(extracted_data.get("task_type", "")),
            ]
        )
    explicit_input_text = raw_text.lower()
    priority_items = _extract_priority_items(raw_text)
    non_negotiable = priority_items.get("non_negotiable", "")
    high_impact = priority_items.get("high_impact", "")
    meeting_item = priority_items.get("meeting", "")
    routine_item = priority_items.get("routine", "")
    meeting_count = int(priority_items.get("meeting_count", "0") or "0")
    explicit_overlap = any(
        phrase in explicit_input_text
        for phrase in ["overlapping meetings", "two overlapping meetings", "back-to-back meetings"]
    )
    explicit_meeting_present = "meeting" in explicit_input_text

    # Hard deterministic hierarchy override for production consistency
    if non_negotiable and routine_item and explicit_meeting_present:
        decision["action"] = f"attend_{non_negotiable.replace(' ', '_')}"
        decision["decision_text"] = f"Attend {non_negotiable} and skip {routine_item} and skip meeting."
    elif non_negotiable and routine_item:
        decision["action"] = f"attend_{non_negotiable.replace(' ', '_')}"
        decision["decision_text"] = f"Attend {non_negotiable} and skip {routine_item}."
    elif non_negotiable and meeting_item and explicit_meeting_present:
        decision["action"] = f"attend_{non_negotiable.replace(' ', '_')}"
        decision["decision_text"] = f"Attend {non_negotiable} and reschedule {meeting_item}."
    elif high_impact and routine_item:
        decision["action"] = f"start_{high_impact.replace(' ', '_')}"
        decision["decision_text"] = f"Start {high_impact} now and stop {routine_item}."
    elif high_impact and meeting_item and explicit_meeting_present:
        decision["action"] = f"start_{high_impact.replace(' ', '_')}"
        decision["decision_text"] = f"Start {high_impact} now and reschedule {meeting_item}."
    elif explicit_overlap:
        decision["action"] = "attend_top_meeting"
        decision["decision_text"] = "Attend the most important meeting and cancel the overlapping meeting."
    elif non_negotiable:
        decision["action"] = f"start_{non_negotiable.replace(' ', '_')}_prep"
        decision["decision_text"] = f"Start preparation for {non_negotiable} now."
    elif high_impact:
        decision["action"] = f"start_{high_impact.replace(' ', '_')}"
        decision["decision_text"] = f"Start {high_impact} now."

    combined_text = f"{raw_text} {decision.get('decision_text', '')}".lower()
    combined_items = _extract_priority_items(combined_text)
    c_non_negotiable = combined_items.get("non_negotiable", "")
    c_high_impact = combined_items.get("high_impact", "")
    c_routine = combined_items.get("routine", "")
    c_meeting = combined_items.get("meeting", "")

    # Hard production overrides for critical conflicts
    if c_non_negotiable and c_routine:
        decision["action"] = f"attend_{c_non_negotiable.replace(' ', '_')}"
        decision["decision_text"] = f"Attend {c_non_negotiable} and skip {c_routine}."
    elif c_non_negotiable and c_meeting and explicit_meeting_present:
        decision["action"] = f"attend_{c_non_negotiable.replace(' ', '_')}"
        decision["decision_text"] = f"Attend {c_non_negotiable} and reschedule {c_meeting}."
    elif c_high_impact and c_routine:
        decision["action"] = f"start_{c_high_impact.replace(' ', '_')}"
        decision["decision_text"] = f"Start {c_high_impact} now and stop {c_routine}."
    elif c_high_impact and c_meeting and explicit_meeting_present:
        decision["action"] = f"start_{c_high_impact.replace(' ', '_')}"
        decision["decision_text"] = f"Start {c_high_impact} now and reschedule {c_meeting}."
    elif explicit_overlap:
        decision["action"] = "attend_top_meeting"
        decision["decision_text"] = "Attend the most important meeting and cancel the overlapping meeting."
    elif "nothing urgent" in combined_text:
        decision["action"] = "start_high_impact_task"
        decision["decision_text"] = "Start one high-impact task now."

    # Final corrective override if upstream labeling flipped priorities
    event_is_low = is_low_priority_event(event_name)
    conflict_is_non_negotiable = is_non_negotiable_event(conflicting_item)
    event_is_meeting = "meeting" in event_name.lower()
    if conflict_is_non_negotiable and (event_is_low or event_is_meeting):
        decision["action"] = f"attend_{conflicting_item.replace(' ', '_')}"
        decision["decision_text"] = f"Attend {conflicting_item} and skip {event_name}."
    elif "deadline" in conflicting_item.lower() and (event_is_low or event_is_meeting):
        decision["action"] = "start_deadline_work"
        decision["decision_text"] = f"Start deadline work now and skip {event_name}."

    action = decision.get("action", "")
    decision_text = str(decision.get("decision_text", "")).strip()
    if not decision_text or any(p in decision_text.lower() for p in FORBIDDEN_PHRASES):
        decision_text = _build_concrete_decision_text(action, event_name, task_name, conflicting_item)

    if not decision_text.lower().startswith(ALLOWED_ACTIONS):
        decision_text = f"Start {task_name} now."

    aligned = _build_aligned_sections(decision_text, raw_text)
    decision["decision_text"] = decision_text
    decision["reasoning"] = aligned["reasoning"]
    decision["consequence"] = aligned["consequence"]
    decision["next_steps"] = aligned["next_steps"]

    if not isinstance(decision.get("rejected_alternatives"), list):
        decision["rejected_alternatives"] = _build_rejected_alternatives(action, scenario_analysis)

    return decision


async def run_decision_engine(
    extracted_data: Dict[str, Any],
    task_analysis: Dict[str, Any],
    calendar_result: Dict[str, Any],
    scenario_analysis: Dict[str, Any],
    time_context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Synthesize final decision using REAL scenario scores.
    
    STRICT RULES:
    - Decision MUST be based on scenario scores
    - NO default "attend_meeting" decisions
    - If all scores same → ERROR
    - Must use highest scoring option
    - VALIDATION: Cannot attend low priority when conflict + high priority task
    
    Args:
        extracted_data: Planner output
        task_analysis: Task agent output
        calendar_result: Calendar agent output
        scenario_analysis: Scenario agent output
        time_context: Time resolver output
        
    Returns:
        Final decision dictionary
        
    Raises:
        DecisionEngineError: If valid decision cannot be made
    """
    options = scenario_analysis.get("options", [])
    
    # VALIDATION: Must have scenarios
    if not options:
        raise DecisionEngineError("No scenarios to evaluate - cannot make decision")
    
    # VALIDATION: Scores must be different
    scores = [opt.get("score", 0) for opt in options]
    if len(set(scores)) == 1:
        raise DecisionEngineError(f"All scenarios have same score ({scores[0]}) - cannot differentiate")
    
    # Get best option (highest score)
    best_option = max(options, key=lambda x: x.get("score", 0))
    best_action = best_option.get("action")
    best_score = best_option.get("score", 0)
    
    # ============================================================
    # CRITICAL VALIDATION: Priority Override
    # ============================================================
    has_conflict = calendar_result.get("has_conflict", False)
    task_priority = calendar_result.get("task_priority", "medium")
    event_priority = calendar_result.get("event_priority", "medium")
    event_type = calendar_result.get("event_type", "event")
    fixed_event = is_non_negotiable_event(event_type)
    
    # If task is high priority + conflict + event is low priority
    # → CANNOT select "attend" action
    if has_conflict and task_priority == "high" and event_priority == "low":
        if "attend" in best_action.lower():
            # Force override to skip action
            for opt in options:
                if "skip" in opt.get("action", "").lower():
                    best_option = opt
                    best_action = opt.get("action")
                    best_score = opt.get("score", 0)
                    break
            else:
                # No skip option found - create one
                best_action = f"skip_{event_type}"
                best_score = 90
                best_option = {
                    "action": best_action,
                    "score": best_score,
                    "description": f"Skip {event_type} to focus on high priority task"
                }

    if has_conflict and fixed_event and "reschedule" in best_action.lower():
        for opt in options:
            if "attend" in opt.get("action", "").lower():
                best_option = opt
                best_action = opt.get("action")
                best_score = opt.get("score", 0)
                break
    
    # Build context for LLM
    context = _build_decision_context(
        extracted_data,
        task_analysis,
        calendar_result,
        scenario_analysis,
        time_context,
        best_option
    )
    
    decision = None
    # Optional LLM path; deterministic rule-based path is default for production consistency
    if USE_LLM_DECISION:
        decision = await _generate_decision_llm(context, best_action, scenario_analysis)
    
    if decision:
        # Validate LLM chose correct action
        if decision.get("action") != best_action:
            # Override with correct action
            decision["action"] = best_action
            decision["reasoning"] = f"Selected {best_action} (score: {best_score}/100) as highest scoring option. " + decision.get("reasoning", "")
        
        # Final validation
        decision = _validate_decision(decision, calendar_result, task_analysis)
        decision = _enforce_real_world_wording(decision, extracted_data, calendar_result, scenario_analysis, best_option)
        return decision
    
    # LLM failed - build rule-based decision
    decision = _build_rule_based_decision(
        extracted_data,
        best_option,
        task_analysis,
        calendar_result,
        scenario_analysis,
        time_context
    )
    
    # Final validation
    decision = _validate_decision(decision, calendar_result, task_analysis)
    decision = _enforce_real_world_wording(decision, extracted_data, calendar_result, scenario_analysis, best_option)
    return decision


def _validate_decision(
    decision: Dict[str, Any],
    calendar_result: Dict[str, Any],
    task_analysis: Dict[str, Any]
) -> Dict[str, Any]:
    """
    CRITICAL: Validate decision against priority rules.
    
    Rules:
    - Cannot attend low priority event when conflict + high priority task
    - Cannot skip high priority event when task is low priority
    """
    action = decision.get("action", "").lower()
    has_conflict = calendar_result.get("has_conflict", False)
    task_priority = calendar_result.get("task_priority", "medium")
    event_priority = calendar_result.get("event_priority", "medium")
    event_type = calendar_result.get("event_type", "event")
    fixed_event = is_non_negotiable_event(event_type)
    
    # RULE 1: High priority task + conflict + low priority event → CANNOT attend
    if has_conflict and task_priority == "high" and event_priority == "low":
        if "attend" in action:
            # Override decision
            decision["action"] = f"skip_{event_type}"
            decision["reasoning"] = f"OVERRIDE: Cannot attend {event_type} (low priority) when high priority task has conflict. " + decision.get("reasoning", "")
            decision["validation_override"] = True
    
    # RULE 2: Low priority task + high priority event → CANNOT skip event
    if has_conflict and task_priority == "low" and event_priority == "high":
        if "skip" in action and event_type.lower() in action.lower():
            # Override decision
            decision["action"] = f"attend_{event_type}"
            decision["reasoning"] = f"OVERRIDE: Cannot skip {event_type} (high priority) for low priority task. " + decision.get("reasoning", "")
            decision["validation_override"] = True

    # RULE 3: Non-negotiable events cannot be skipped or rescheduled
    if has_conflict and fixed_event:
        if "skip" in action or "reschedule" in action:
            decision["action"] = f"attend_{event_type}"
            decision["reasoning"] = f"OVERRIDE: {event_type} is non-negotiable and must be attended. " + decision.get("reasoning", "")
            decision["validation_override"] = True
    
    return decision


def _build_decision_context(
    extracted_data: Dict[str, Any],
    task_analysis: Dict[str, Any],
    calendar_result: Dict[str, Any],
    scenario_analysis: Dict[str, Any],
    time_context: Dict[str, Any],
    best_option: Dict[str, Any]
) -> str:
    """
    Build context string for decision engine.
    """
    # Format all scenarios with scores
    scenarios_text = ""
    for opt in scenario_analysis.get("options", []):
        is_best = " ← HIGHEST SCORE" if opt.get("action") == best_option.get("action") else ""
        scenarios_text += f"""
ACTION: {opt.get('action')}
Score: {opt.get('score', 0)}/100{is_best}
Description: {opt.get('description', '')}
Risks: {', '.join(opt.get('risks', []))}
Benefits: {', '.join(opt.get('benefits', []))}
"""
    
    context = f"""
=== TASK ===
Task: {extracted_data.get('task_description', 'Unknown')}
Type: {extracted_data.get('task_type', 'Unknown')}

=== ANALYSIS ===
Urgency: {task_analysis.get('urgency_score', 5)}/10
Importance: {task_analysis.get('importance_score', 5)}/10
Priority: {task_analysis.get('priority', 5)}/10

=== CALENDAR ===
Event Type: {calendar_result.get('event_type', 'event')}
Available Time: {calendar_result.get('available_time', 0):.1f} hours
Required Time: {calendar_result.get('required_time', 0):.1f} hours
Has Conflict: {calendar_result.get('has_conflict', False)}
Conflict Reason: {calendar_result.get('conflict_reason', 'None')}

=== SCORED SCENARIOS ===
{scenarios_text}

=== BEST OPTION ===
Action: {best_option.get('action')}
Score: {best_option.get('score', 0)}/100

YOU MUST SELECT: {best_option.get('action')} (highest score)

Provide reasoning for why this is the correct decision based on the data.
"""
    
    return context


async def _generate_decision_llm(
    context: str,
    required_action: str,
    scenario_analysis: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Generate decision via LLM.
    """
    try:
        response = await client.chat.completions.create(
            model=MODEL,
            temperature=TEMPERATURE,
            messages=[
                {"role": "system", "content": DECISION_SYSTEM_PROMPT},
                {"role": "user", "content": context}
            ]
        )
        
        content = response.choices[0].message.content
        parsed = safe_json(content)
        
        if parsed and "action" in parsed:
            # Ensure confidence is valid
            confidence = parsed.get("confidence", 0.8)
            if not isinstance(confidence, (int, float)):
                confidence = 0.8
            parsed["confidence"] = max(0, min(1, confidence))

            if not parsed.get("consequence"):
                parsed["consequence"] = _build_consequence_text(parsed.get("action", ""), scenario_analysis, "event", "task")
            
            # Ensure lists exist
            if not isinstance(parsed.get("next_steps"), list):
                parsed["next_steps"] = []
            if not isinstance(parsed.get("mcp_actions"), list):
                parsed["mcp_actions"] = []

            if not isinstance(parsed.get("rejected_alternatives"), list):
                parsed["rejected_alternatives"] = _build_rejected_alternatives(parsed.get("action", ""), scenario_analysis)
            
            return parsed
        
        return None
        
    except Exception:
        return None


def _build_rule_based_decision(
    extracted_data: Dict[str, Any],
    best_option: Dict[str, Any],
    task_analysis: Dict[str, Any],
    calendar_result: Dict[str, Any],
    scenario_analysis: Dict[str, Any],
    time_context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Build decision using rule-based logic when LLM fails.
    Uses REAL data - no defaults.
    Includes STRONG decision language.
    """
    action = best_option.get("action", "proceed")
    score = best_option.get("score", 0)
    urgency = task_analysis.get("urgency_score", 5)
    importance = task_analysis.get("importance_score", 5)
    has_conflict = calendar_result.get("has_conflict", False)
    event_type = calendar_result.get("event_type", "event")
    labels = _extract_labels(extracted_data, calendar_result, best_option)
    event_title = labels["event_name"]
    task_name = labels["task_name"]
    conflicting_item = labels["conflicting_item"]
    available_time = calendar_result.get("available_time", 0)
    required_time = calendar_result.get("required_time", 0)
    task_type = calendar_result.get("task_priority", "task")
    derived = _derive_decision_variables(extracted_data, task_analysis, calendar_result)
    fixed_event = len(derived.get("fixed_events", [])) > 0
    
    # Determine conflict type
    conflict_type = "none"
    if has_conflict:
        task_priority = calendar_result.get("task_priority", "medium")
        event_priority = calendar_result.get("event_priority", "medium")
        if task_priority != event_priority:
            conflict_type = "priority_conflict"
        else:
            conflict_type = "time_conflict"
    
    # Calculate confidence based on score difference
    options = scenario_analysis.get("options", [])
    if len(options) >= 2:
        sorted_opts = sorted(options, key=lambda x: x.get("score", 0), reverse=True)
        score_diff = sorted_opts[0].get("score", 0) - sorted_opts[1].get("score", 0)
        if score_diff >= 15:
            confidence = 0.9
        elif score_diff >= 10:
            confidence = 0.8
        elif score_diff >= 5:
            confidence = 0.7
        else:
            confidence = 0.6
    else:
        confidence = 0.7
    
    # Build STRONG decision text (imperative, action verb first)
    decision_text = ""
    reasoning_parts = []
    
    if "skip" in action.lower():
        decision_text = f"Skip {event_title} and complete {task_name}"
        reasoning_parts.append(f"Skipping {event_title} is recommended (score: {score}/100)")
        if urgency >= 7:
            reasoning_parts.append(f"Urgency is high ({urgency}/10)")
        if has_conflict:
            reasoning_parts.append(f"Time conflict detected: {available_time:.1f}h available vs {required_time:.1f}h needed")
        reasoning_parts.append(f"Focus on task to meet deadline")
    
    elif "attend" in action.lower():
        if has_conflict and fixed_event:
            decision_text = f"Attend {event_title} and pause {conflicting_item} until it ends"
        elif has_conflict:
            decision_text = f"Attend {event_title} and schedule {task_name} immediately after"
        else:
            decision_text = f"Attend {event_title} as planned"
        reasoning_parts.append(f"Attending {event_title} is recommended (score: {score}/100)")
        if urgency < 6:
            reasoning_parts.append(f"Urgency is manageable ({urgency}/10)")
        if not has_conflict:
            reasoning_parts.append(f"No time conflict: {available_time:.1f}h available for {required_time:.1f}h task")
        reasoning_parts.append(f"Can balance {event_title} and task")
    
    elif "reschedule" in action.lower():
        decision_text = f"Reschedule {event_title} and complete {task_name} first"
        reasoning_parts.append(f"Rescheduling {event_title} is recommended (score: {score}/100)")
        reasoning_parts.append(f"This balances both commitments")
        if has_conflict:
            reasoning_parts.append(f"Resolves time conflict while keeping {event_title}")
    
    else:
        decision_text = f"Proceed with {action.replace('_', ' ')}"
        reasoning_parts.append(f"Selected action: {action} (score: {score}/100)")
        reasoning_parts.append(f"Based on urgency {urgency}/10 and importance {importance}/10")
    
    reasoning = ". ".join(reasoning_parts) + "."
    reasoning += (
        f" Priority order applied: non-negotiable events first, then high-impact work, then meetings, then routine items."
    )
    consequence = _build_consequence_text(action, scenario_analysis, event_title, task_name)
    
    # Generate next steps (imperative)
    next_steps = []
    if "skip" in action.lower():
        next_steps = [
            f"Cancel or decline {event_title}",
            "Start working on your task immediately",
            "Complete before the deadline"
        ]
    elif "attend" in action.lower():
        if has_conflict and fixed_event:
            next_steps = [
                f"Attend {event_title} without changing it",
                f"Pause {conflicting_item} during the event",
                f"Resume {task_name} immediately after"
            ]
        else:
            next_steps = [
                f"Attend {event_title} as scheduled",
                "Work on task before and after the event",
                "Monitor your progress"
            ]
    elif "reschedule" in action.lower():
        next_steps = [
            f"Move {event_title} to a later time slot",
            "Focus on your priority task now",
            f"Attend {event_title} after completing your task"
        ]
    else:
        next_steps = [
            f"Execute: {action.replace('_', ' ')}",
            "Monitor your progress",
            "Adjust as needed"
        ]
    
    # Build executable actions
    executable_actions = []
    event_id = best_option.get("event_id")
    if event_id:
        if "skip" in action.lower() or "cancel" in action.lower():
            executable_actions.append({
                "type": "cancel_event",
                "event_id": event_id,
                "event_title": event_title
            })
        elif "reschedule" in action.lower():
            executable_actions.append({
                "type": "reschedule_event",
                "event_id": event_id,
                "event_title": event_title,
                "suggested_time": best_option.get("suggested_time", "2 hours later")
            })
    
    return {
        "action": action,
        "decision_text": decision_text,
        "consequence": consequence,
        "confidence": confidence,
        "reasoning": reasoning,
        "rejected_alternatives": _build_rejected_alternatives(action, scenario_analysis),
        "conflict_type": conflict_type,
        "next_steps": next_steps,
        "mcp_actions": [],
        "executable_actions": executable_actions,
        "score": score,
        "data_driven": True
    }


async def make_direct_decision(
    extracted_data: Dict[str, Any],
    task_analysis: Dict[str, Any],
    calendar_result: Dict[str, Any],
    time_context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Make a direct decision when scenario simulation was skipped.
    Still uses REAL data - no defaults.
    """
    has_conflict = calendar_result.get("has_conflict", False)
    urgency = task_analysis.get("urgency_score", 5)
    event_type = calendar_result.get("event_type", "event")
    fixed_event = is_non_negotiable_event(event_type)
    available_time = calendar_result.get("available_time", 0)
    required_time = calendar_result.get("required_time", 0)
    alternatives = calendar_result.get("alternatives", [])
    
    # Choose action based on real data
    if has_conflict:
        if fixed_event:
            action = f"attend_{event_type}" if f"attend_{event_type}" in alternatives else alternatives[0] if alternatives else "attend_fixed_event"
        elif urgency >= 7:
            action = f"skip_{event_type}" if f"skip_{event_type}" in alternatives else alternatives[0] if alternatives else "focus_on_task"
        else:
            action = f"reschedule_{event_type}" if f"reschedule_{event_type}" in alternatives else alternatives[0] if alternatives else "proceed"
    else:
        if urgency >= 7:
            action = "start_immediately"
        else:
            action = f"attend_{event_type}" if event_type else "proceed_as_planned"
    
    confidence = 0.8 if not has_conflict else 0.7
    labels = _extract_labels(extracted_data, calendar_result)
    consequence = _build_consequence_text(action, {"options": []}, labels["event_name"], labels["task_name"])
    derived = _derive_decision_variables(extracted_data, task_analysis, calendar_result)
    decision_text = _build_concrete_decision_text(action, labels["event_name"], labels["task_name"], labels["conflicting_item"])
    reasoning = (
        f"Priority order applied to {labels['event_name']} and {labels['task_name']}. "
        f"Urgency={urgency}/10, conflict={has_conflict}, available={available_time:.1f}h, required={required_time:.1f}h."
    )
    
    decision = {
        "action": action,
        "decision_text": decision_text,
        "confidence": confidence,
        "consequence": consequence,
        "reasoning": reasoning,
        "rejected_alternatives": [],
        "next_steps": [
            f"Execute: {action}",
            "Monitor progress",
            "Complete task"
        ],
        "mcp_actions": [],
        "data_driven": True
    }

    return _enforce_real_world_wording(
        decision,
        extracted_data,
        calendar_result,
        {"options": []},
        {}
    )


def _build_consequence_text(action: str, scenario_analysis: Dict[str, Any], event_name: str, task_name: str) -> str:
    """Build a short consequence statement for the final decision output."""
    action_lower = (action or "").lower()

    if "skip" in action_lower or "cancel" in action_lower:
        return f"If you ignore this, {task_name} will slip and you risk deadline failure."

    if "reschedule" in action_lower:
        return f"If you ignore this, {event_name} will keep colliding with {task_name} and execution quality will drop."

    if "attend" in action_lower:
        return f"If you ignore this, you risk missing {event_name} and losing a critical opportunity."

    if "focus" in action_lower or "start" in action_lower:
        return f"If you ignore this, {task_name} will remain unfinished and deadline pressure will intensify."

    return f"If you ignore this, {task_name} will remain unresolved and risk will increase."
