"""
Scenario Agent for DecisionOS.
HYBRID agent - generates EXACTLY 3 scenarios with DIFFERENT scores.
Uses rule-based scoring that PENALIZES/REWARDS based on urgency and priority.

CRITICAL RULES:
- If conflict exists AND task is HIGH priority:
  * attending low priority event = score < 30
  * skipping low priority event = score > 80
- MUST trigger when has_conflict == True
"""

import os
from typing import Dict, Any, List
from openai import AsyncOpenAI

from ai_engine.utils.helpers import safe_json
from ai_engine.config.defaults import (
    SCORING_WEIGHTS,
    CONFLICT_SCORE_PENALTIES,
    classify_event_priority,
    is_high_priority_task,
    is_low_priority_event
)

# Initialize Gemini client
client = AsyncOpenAI(
    api_key=os.environ.get("GEMINI_API_KEY", ""),
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
)

MODEL = "gemini-2.0-flash"
TEMPERATURE = 0.3


class ScenarioAgentError(Exception):
    """Raised when scenario agent fails validation."""
    pass


SCENARIO_SYSTEM_PROMPT = """You are a scenario simulation agent. Generate realistic outcomes for EXACTLY 3 alternative actions.

Given the context, generate detailed outcomes for each action.

OUTPUT FORMAT (JSON only):
{
    "scenarios": [
        {
            "action": "<action name>",
            "description": "<what happens if this action is taken>",
            "task_impact": "<direct impact on the main task/deadline>",
            "consequences": "<other consequences of this choice>",
            "risks": ["<risk 1>", "<risk 2>"],
            "benefits": ["<benefit 1>", "<benefit 2>"]
        }
    ]
}

RULES:
1. Generate EXACTLY 3 scenarios - one for each alternative
2. Be specific to the situation - not generic
3. Consider real trade-offs
4. Output valid JSON only
"""


async def run_scenario_agent(
    extracted_data: Dict[str, Any],
    task_analysis: Dict[str, Any],
    calendar_result: Dict[str, Any],
    time_context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Generate and score EXACTLY 3 scenarios with DIFFERENT scores.
    
    STRICT REQUIREMENTS:
    - MUST generate exactly 3 scenarios
    - Scores MUST be different
    - Skip penalized when urgency high
    - Attend penalized when deadline close
    - Reschedule gets moderate score
    
    Args:
        extracted_data: Planner output
        task_analysis: Task agent output
        calendar_result: Calendar agent output
        time_context: Time resolver output
        
    Returns:
        Dictionary with exactly 3 scored scenarios
        
    Raises:
        ScenarioAgentError: If scenarios cannot be generated
    """
    raw_alternatives = calendar_result.get("alternatives", [])
    
    # Handle new dict format or old string format
    alternatives = []
    alternative_details = {}  # Store full details for MCP actions
    
    for alt in raw_alternatives:
        if isinstance(alt, dict):
            action = alt.get("action", "unknown")
            alternatives.append(action)
            alternative_details[action] = alt
        else:
            alternatives.append(alt)
            alternative_details[alt] = {"action": alt}
    
    # MUST have alternatives
    if not alternatives or len(alternatives) < 3:
        # Generate default alternatives based on event type
        event_type = calendar_result.get("event_type", "event")
        alternatives = [
            f"attend_{event_type}",
            f"skip_{event_type}",
            f"reschedule_{event_type}"
        ]
        alternative_details = {a: {"action": a} for a in alternatives}
    
    # Take exactly 3 alternatives
    alternatives = alternatives[:3]
    
    # Try to generate rich scenarios via LLM
    scenarios = await _generate_scenarios_llm(
        extracted_data,
        task_analysis,
        calendar_result,
        time_context,
        alternatives
    )
    
    # If LLM failed, generate rule-based scenarios
    if not scenarios or len(scenarios) < 3:
        scenarios = _generate_scenarios_rule_based(
            extracted_data,
            task_analysis,
            calendar_result,
            alternatives
        )
    
    # CRITICAL: Score scenarios with FORCED DIFFERENTIATION
    scored_scenarios = _score_scenarios_differentiated(
        scenarios,
        task_analysis,
        calendar_result,
        time_context
    )
    
    # VALIDATION: Ensure different scores
    scores = [s["score"] for s in scored_scenarios]
    if len(set(scores)) < len(scores):
        # Scores are same - force differentiation
        scored_scenarios = _force_score_differentiation(scored_scenarios)
    
    # Add event details for MCP execution
    for scenario in scored_scenarios:
        action = scenario.get("action", "")
        if action in alternative_details:
            details = alternative_details[action]
            scenario["event_id"] = details.get("event_id")
            scenario["event_title"] = details.get("event_title")
            scenario["mcp_action"] = details.get("mcp_action")
            scenario["suggested_time"] = details.get("suggested_time")
    
    # Get recommendation (highest score)
    recommendation = scored_scenarios[0]["action"]
    
    return {
        "options": scored_scenarios,
        "recommendation": recommendation,
        "scenario_count": len(scored_scenarios),
        "scores_unique": len(set(s["score"] for s in scored_scenarios)) == len(scored_scenarios),
        "primary_event": calendar_result.get("primary_event")
    }


async def _generate_scenarios_llm(
    extracted_data: Dict[str, Any],
    task_analysis: Dict[str, Any],
    calendar_result: Dict[str, Any],
    time_context: Dict[str, Any],
    alternatives: List[str]
) -> List[Dict[str, Any]]:
    """
    Generate scenario descriptions via LLM.
    """
    context = f"""
SITUATION:
- Task: {extracted_data.get('task_description', 'Unknown task')}
- Task Type: {extracted_data.get('task_type', 'Unknown')}
- Urgency: {task_analysis.get('urgency_score', 5)}/10
- Importance: {task_analysis.get('importance_score', 5)}/10
- Event: {calendar_result.get('event_type', 'event')}
- Has Conflict: {calendar_result.get('has_conflict', False)}
- Conflict Reason: {calendar_result.get('conflict_reason', 'None')}
- Available Time: {calendar_result.get('available_time', 0):.1f}h
- Required Time: {calendar_result.get('required_time', 0):.1f}h

ALTERNATIVES TO EVALUATE:
1. {alternatives[0]}
2. {alternatives[1]}
3. {alternatives[2]}

Generate realistic outcomes for each alternative.
"""
    
    try:
        response = await client.chat.completions.create(
            model=MODEL,
            temperature=TEMPERATURE,
            messages=[
                {"role": "system", "content": SCENARIO_SYSTEM_PROMPT},
                {"role": "user", "content": context}
            ]
        )
        
        content = response.choices[0].message.content
        parsed = safe_json(content)
        
        if parsed and "scenarios" in parsed:
            return parsed["scenarios"]
        
        return []
        
    except Exception:
        return []


def _generate_scenarios_rule_based(
    extracted_data: Dict[str, Any],
    task_analysis: Dict[str, Any],
    calendar_result: Dict[str, Any],
    alternatives: List[str]
) -> List[Dict[str, Any]]:
    """
    Generate scenarios using rule-based logic when LLM fails.
    """
    task_type = extracted_data.get("task_type", "task")
    event_type = calendar_result.get("event_type", "event")
    urgency = task_analysis.get("urgency_score", 5)
    has_conflict = calendar_result.get("has_conflict", False)
    
    scenarios = []
    
    for action in alternatives:
        action_lower = action.lower()
        
        if "attend" in action_lower:
            if has_conflict and urgency >= 7:
                scenario = {
                    "action": action,
                    "description": f"Attend {event_type} despite tight deadline",
                    "task_impact": f"Risk missing {task_type} deadline or delivering poor quality",
                    "consequences": "Maintains relationship but risks task failure",
                    "risks": ["May miss deadline", "Rushed work quality", "Increased stress"],
                    "benefits": ["Maintains commitment", "Social/professional obligation met"]
                }
            else:
                scenario = {
                    "action": action,
                    "description": f"Attend {event_type} as planned",
                    "task_impact": f"Can work on {task_type} before and after",
                    "consequences": "Balanced approach if time permits",
                    "risks": ["Less focused time", "Potential time pressure"],
                    "benefits": ["Keeps commitment", "Mental break from work"]
                }
        
        elif "skip" in action_lower:
            if urgency >= 7:
                scenario = {
                    "action": action,
                    "description": f"Skip {event_type} to focus on {task_type}",
                    "task_impact": f"Maximum time for {task_type}, higher chance of success",
                    "consequences": f"Miss {event_type} but prioritize deadline",
                    "risks": [f"Miss {event_type} benefits", "May need to explain absence"],
                    "benefits": ["Full focus on task", "Better quality work", "Meet deadline"]
                }
            else:
                scenario = {
                    "action": action,
                    "description": f"Skip {event_type} for extra work time",
                    "task_impact": f"More time for {task_type}",
                    "consequences": f"Unnecessary sacrifice of {event_type}",
                    "risks": [f"Miss {event_type}", "Over-prioritizing work"],
                    "benefits": ["Extra buffer time", "Less time pressure"]
                }
        
        elif "reschedule" in action_lower:
            scenario = {
                "action": action,
                "description": f"Reschedule {event_type} to after deadline",
                "task_impact": f"Can focus on {task_type} now, {event_type} later",
                "consequences": "Balanced solution if rescheduling is possible",
                "risks": [f"May not be able to reschedule {event_type}", "Adds planning overhead"],
                "benefits": ["Keeps both commitments", "Reduces conflict", "Flexible approach"]
            }
        
        else:
            scenario = {
                "action": action,
                "description": f"Execute: {action}",
                "task_impact": "Impact depends on execution",
                "consequences": "Outcome varies",
                "risks": ["Uncertainty"],
                "benefits": ["Takes action"]
            }
        
        scenarios.append(scenario)
    
    return scenarios


def _score_scenarios_differentiated(
    scenarios: List[Dict[str, Any]],
    task_analysis: Dict[str, Any],
    calendar_result: Dict[str, Any],
    time_context: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Score scenarios with FORCED DIFFERENTIATION and HARD PENALTIES.
    
    CRITICAL SCORING RULES:
    - If conflict exists AND task is HIGH priority (exam, deadline):
      * Skip low priority event = score > 80
      * Attend low priority event = score < 30
    - If conflict exists AND event is HIGH priority:
      * Attend = score > 70
      * Skip = score < 40
    
    Standard rules:
    - Skip: REWARD when urgency >= 7, PENALIZE when urgency < 5
    - Attend: PENALIZE when urgency >= 7, REWARD when urgency < 5
    - Reschedule: Moderate score, slight reward when conflict exists
    """
    urgency = task_analysis.get("urgency_score", 5)
    importance = task_analysis.get("importance_score", 5)
    has_conflict = calendar_result.get("has_conflict", False)
    available_time = calendar_result.get("available_time", 8)
    required_time = calendar_result.get("required_time", 2)
    
    # Get priority classifications
    task_priority = calendar_result.get("task_priority", "medium")
    event_priority = calendar_result.get("event_priority", "medium")
    event_type = calendar_result.get("event_type", "event")
    
    # Also check from extracted data for task type
    task_type = task_analysis.get("task_type", "")
    if not task_priority or task_priority == "medium":
        task_priority = classify_event_priority(task_type)
    
    # Time pressure factor (0-1, higher = more pressure)
    if required_time > 0:
        time_pressure = max(0, min(1, 1 - (available_time - required_time) / required_time))
    else:
        time_pressure = 0
    
    scored = []
    
    for scenario in scenarios:
        action = scenario.get("action", "").lower()
        
        # Base score from urgency and importance
        base_score = (urgency * 4 + importance * 3) / 7 * 10  # 0-100 base
        
        # ============================================================
        # HARD PENALTY RULES (CRITICAL)
        # ============================================================
        
        # RULE 1: High priority task + conflict + low priority event
        # Example: exam + conflict + gym → MUST skip gym
        if has_conflict and task_priority == "high" and event_priority == "low":
            if "skip" in action:
                # FORCE high score for skipping low priority
                score = max(85, base_score + 30)
            elif "attend" in action:
                # FORCE low score for attending low priority
                score = min(25, base_score - 40)
            elif "reschedule" in action:
                score = max(75, base_score + 15)
            else:
                score = base_score
        
        # RULE 2: Low priority task + high priority event
        # Example: casual work + important meeting → attend meeting
        elif has_conflict and task_priority == "low" and event_priority == "high":
            if "attend" in action:
                score = max(80, base_score + 25)
            elif "skip" in action:
                score = min(30, base_score - 35)
            elif "reschedule" in action:
                score = 60
            else:
                score = base_score
        
        # RULE 3: Both high priority - favor task if urgency high
        elif has_conflict and task_priority == "high" and event_priority == "high":
            if urgency >= 8:
                if "skip" in action:
                    score = base_score + 20
                elif "attend" in action:
                    score = base_score - 15
                else:
                    score = base_score + 5
            else:
                if "reschedule" in action:
                    score = base_score + 15
                else:
                    score = base_score
        
        # RULE 4: Standard scoring when no hard rules apply
        else:
            # Action-specific adjustments
            if "skip" in action:
                # Skip is GOOD when urgent, BAD when not urgent
                if urgency >= 8:
                    score = base_score + 25 + (time_pressure * 15)
                elif urgency >= 6:
                    score = base_score + 15 + (time_pressure * 10)
                elif urgency >= 4:
                    score = base_score - 5
                else:
                    score = base_score - 20  # Low urgency - skipping is bad
            
            elif "attend" in action:
                # Attend is BAD when urgent, GOOD when not urgent
                if urgency >= 8:
                    score = base_score - 25 - (time_pressure * 15)
                elif urgency >= 6:
                    score = base_score - 15 - (time_pressure * 10)
                elif urgency >= 4:
                    score = base_score + 5
                else:
                    score = base_score + 20  # Low urgency - attending is good
            
            elif "reschedule" in action:
                # Reschedule is moderate - good when conflict, neutral otherwise
                if has_conflict:
                    score = base_score + 10
                else:
                    score = base_score
                # Slight boost for being a compromise
                score += 3
            
            else:
                # Default scoring
                score = base_score
        
        # Conflict bonus for task-focused actions
        if has_conflict and ("skip" in action or "prioritize" in action):
            score += 5
        
        # Ensure score is in valid range
        score = max(5, min(95, score))
        
        scored_scenario = {
            **scenario,
            "score": round(score, 1),
            "urgency_factor": urgency,
            "time_pressure": round(time_pressure, 2),
            "task_priority": task_priority,
            "event_priority": event_priority
        }
        scored.append(scored_scenario)
    
    # Sort by score descending
    scored.sort(key=lambda x: x["score"], reverse=True)
    
    return scored


def _force_score_differentiation(scenarios: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Force scores to be different if they ended up the same.
    """
    if len(scenarios) < 2:
        return scenarios
    
    # Sort by current score
    scenarios.sort(key=lambda x: x["score"], reverse=True)
    
    # Ensure each score is different
    for i in range(1, len(scenarios)):
        if scenarios[i]["score"] >= scenarios[i-1]["score"]:
            # Force lower score
            scenarios[i]["score"] = scenarios[i-1]["score"] - 5
    
    # Ensure no score below 5
    for s in scenarios:
        s["score"] = max(5, s["score"])
    
    return scenarios
