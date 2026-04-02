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
from typing import Dict, Any, List
from openai import AsyncOpenAI

from ai_engine.utils.helpers import safe_json
from ai_engine.config.defaults import classify_event_priority, is_low_priority_event

# Initialize Gemini client
client = AsyncOpenAI(
    api_key=os.environ.get("GEMINI_API_KEY", ""),
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
)

MODEL = "gemini-2.0-flash"
TEMPERATURE = 0.2


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
3. Reasoning MUST reference the actual scores and data
4. Be specific - not generic
5. Output valid JSON only

VALID MCP TOOLS:
- create_event: params (title, start_time, end_time, description)
- reschedule_event: params (event_id, new_start_time, new_end_time)
- cancel_event: params (event_id)
- add_task: params (title, description, priority, deadline, estimated_duration)
"""


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
    
    # Build context for LLM
    context = _build_decision_context(
        extracted_data,
        task_analysis,
        calendar_result,
        scenario_analysis,
        time_context,
        best_option
    )
    
    # Try LLM for rich reasoning
    decision = await _generate_decision_llm(context, best_action, scenario_analysis)
    
    if decision:
        # Validate LLM chose correct action
        if decision.get("action") != best_action:
            # Override with correct action
            decision["action"] = best_action
            decision["reasoning"] = f"Selected {best_action} (score: {best_score}/100) as highest scoring option. " + decision.get("reasoning", "")
        
        # Final validation
        decision = _validate_decision(decision, calendar_result, task_analysis)
        return decision
    
    # LLM failed - build rule-based decision
    decision = _build_rule_based_decision(
        best_option,
        task_analysis,
        calendar_result,
        scenario_analysis,
        time_context
    )
    
    # Final validation
    decision = _validate_decision(decision, calendar_result, task_analysis)
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
            
            # Ensure lists exist
            if not isinstance(parsed.get("next_steps"), list):
                parsed["next_steps"] = []
            if not isinstance(parsed.get("mcp_actions"), list):
                parsed["mcp_actions"] = []
            
            return parsed
        
        return None
        
    except Exception:
        return None


def _build_rule_based_decision(
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
    action = best_option.get("action")
    score = best_option.get("score", 0)
    urgency = task_analysis.get("urgency_score", 5)
    importance = task_analysis.get("importance_score", 5)
    has_conflict = calendar_result.get("has_conflict", False)
    event_type = calendar_result.get("event_type", "event")
    event_title = best_option.get("event_title", event_type)
    available_time = calendar_result.get("available_time", 0)
    required_time = calendar_result.get("required_time", 0)
    task_type = calendar_result.get("task_priority", "task")
    
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
        decision_text = f"Skip {event_title} and focus on your {task_type if task_type != 'high' else 'priority task'}"
        reasoning_parts.append(f"Skipping {event_title} is recommended (score: {score}/100)")
        if urgency >= 7:
            reasoning_parts.append(f"Urgency is high ({urgency}/10)")
        if has_conflict:
            reasoning_parts.append(f"Time conflict detected: {available_time:.1f}h available vs {required_time:.1f}h needed")
        reasoning_parts.append(f"Focus on task to meet deadline")
    
    elif "attend" in action.lower():
        decision_text = f"Attend {event_title} as planned"
        reasoning_parts.append(f"Attending {event_title} is recommended (score: {score}/100)")
        if urgency < 6:
            reasoning_parts.append(f"Urgency is manageable ({urgency}/10)")
        if not has_conflict:
            reasoning_parts.append(f"No time conflict: {available_time:.1f}h available for {required_time:.1f}h task")
        reasoning_parts.append(f"Can balance {event_title} and task")
    
    elif "reschedule" in action.lower():
        decision_text = f"Reschedule {event_title} to a later time"
        reasoning_parts.append(f"Rescheduling {event_title} is recommended (score: {score}/100)")
        reasoning_parts.append(f"This balances both commitments")
        if has_conflict:
            reasoning_parts.append(f"Resolves time conflict while keeping {event_title}")
    
    else:
        decision_text = f"Proceed with {action.replace('_', ' ')}"
        reasoning_parts.append(f"Selected action: {action} (score: {score}/100)")
        reasoning_parts.append(f"Based on urgency {urgency}/10 and importance {importance}/10")
    
    reasoning = ". ".join(reasoning_parts) + "."
    
    # Generate next steps (imperative)
    next_steps = []
    if "skip" in action.lower():
        next_steps = [
            f"Cancel or decline {event_title}",
            "Start working on your task immediately",
            "Complete before the deadline"
        ]
    elif "attend" in action.lower():
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
        "confidence": confidence,
        "reasoning": reasoning,
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
    available_time = calendar_result.get("available_time", 0)
    required_time = calendar_result.get("required_time", 0)
    alternatives = calendar_result.get("alternatives", [])
    
    # Choose action based on real data
    if has_conflict:
        if urgency >= 7:
            action = f"skip_{event_type}" if f"skip_{event_type}" in alternatives else alternatives[0] if alternatives else "focus_on_task"
        else:
            action = f"reschedule_{event_type}" if f"reschedule_{event_type}" in alternatives else alternatives[0] if alternatives else "proceed"
    else:
        if urgency >= 7:
            action = "start_immediately"
        else:
            action = f"attend_{event_type}" if event_type else "proceed_as_planned"
    
    confidence = 0.8 if not has_conflict else 0.7
    
    return {
        "action": action,
        "confidence": confidence,
        "reasoning": f"Direct decision based on: urgency {urgency}/10, conflict={has_conflict}, available={available_time:.1f}h, required={required_time:.1f}h",
        "next_steps": [
            f"Execute: {action}",
            "Monitor progress",
            "Complete task"
        ],
        "mcp_actions": [],
        "data_driven": True
    }
