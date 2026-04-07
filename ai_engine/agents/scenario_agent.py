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
import google.generativeai as genai

from ai_engine.utils.helpers import safe_json
from ai_engine.config.defaults import (
    SCORING_WEIGHTS,
    CONFLICT_SCORE_PENALTIES,
    classify_event_priority,
)

# Configure Gemini
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

MODEL = "gemini-2.0-flash"
TEMPERATURE = 0.3


class ScenarioAgentError(Exception):
    pass


SCENARIO_SYSTEM_PROMPT = """You are a scenario simulation agent. Generate realistic outcomes for EXACTLY 3 alternative actions.

OUTPUT FORMAT (JSON only):
{
    "scenarios": [
        {
            "action": "<action name>",
            "description": "<what happens>",
            "task_impact": "<impact on task>",
            "consequences": "<other consequences>",
            "risks": ["risk1", "risk2"],
            "benefits": ["benefit1", "benefit2"]
        }
    ]
}

RULES:
- EXACTLY 3 scenarios
- Be specific
- Output JSON only
"""


async def run_scenario_agent(
    extracted_data: Dict[str, Any],
    task_analysis: Dict[str, Any],
    calendar_result: Dict[str, Any],
    time_context: Dict[str, Any]
) -> Dict[str, Any]:

    raw_alternatives = calendar_result.get("alternatives", [])

    alternatives = []
    alternative_details = {}

    for alt in raw_alternatives:
        if isinstance(alt, dict):
            action = alt.get("action", "unknown")
            alternatives.append(action)
            alternative_details[action] = alt
        else:
            alternatives.append(alt)
            alternative_details[alt] = {"action": alt}

    if not alternatives or len(alternatives) < 3:
        event_type = calendar_result.get("event_type", "event")
        alternatives = [
            f"attend_{event_type}",
            f"skip_{event_type}",
            f"reschedule_{event_type}"
        ]
        alternative_details = {a: {"action": a} for a in alternatives}

    alternatives = alternatives[:3]

    # Try LLM
    scenarios = await _generate_scenarios_llm(
        extracted_data,
        task_analysis,
        calendar_result,
        alternatives
    )

    if not scenarios or len(scenarios) < 3:
        scenarios = _generate_scenarios_rule_based(
            extracted_data,
            task_analysis,
            calendar_result,
            alternatives
        )

    scored = _score_scenarios_differentiated(
        scenarios,
        task_analysis,
        calendar_result
    )

    scores = [s["score"] for s in scored]
    if len(set(scores)) < len(scores):
        scored = _force_score_differentiation(scored)

    for scenario in scored:
        action = scenario.get("action", "")
        if action in alternative_details:
            details = alternative_details[action]
            scenario["event_id"] = details.get("event_id")
            scenario["event_title"] = details.get("event_title")

    return {
        "options": scored,
        "recommendation": scored[0]["action"],
        "scenario_count": len(scored),
        "scores_unique": len(set(s["score"] for s in scored)) == len(scored),
        "primary_event": calendar_result.get("primary_event")
    }


async def _generate_scenarios_llm(
    extracted_data,
    task_analysis,
    calendar_result,
    alternatives
):

    context = f"""
Task: {extracted_data.get('task_description')}
Urgency: {task_analysis.get('urgency_score')}
Event: {calendar_result.get('event_type')}

Alternatives:
1. {alternatives[0]}
2. {alternatives[1]}
3. {alternatives[2]}
"""

    try:
        model = genai.GenerativeModel(
            model_name=MODEL,
            generation_config={"temperature": TEMPERATURE}
        )

        response = model.generate_content(
            f"{SCENARIO_SYSTEM_PROMPT}\n\n{context}"
        )

        parsed = safe_json(response.text)

        if parsed and "scenarios" in parsed:
            return parsed["scenarios"]

    except Exception:
        return []

    return []


def _generate_scenarios_rule_based(
    extracted_data,
    task_analysis,
    calendar_result,
    alternatives
):

    task = extracted_data.get("task_type", "task")
    event = calendar_result.get("event_type", "event")
    urgency = task_analysis.get("urgency_score", 5)

    scenarios = []

    for action in alternatives:

        if "attend" in action:
            scenarios.append({
                "action": action,
                "description": f"Attend {event}",
                "task_impact": f"Less time for {task}",
                "consequences": "Possible delay",
                "risks": ["Time loss"],
                "benefits": ["Commitment kept"]
            })

        elif "skip" in action:
            scenarios.append({
                "action": action,
                "description": f"Skip {event}",
                "task_impact": f"More time for {task}",
                "consequences": "Miss event",
                "risks": ["Lost opportunity"],
                "benefits": ["Better task focus"]
            })

        else:
            scenarios.append({
                "action": action,
                "description": f"Reschedule {event}",
                "task_impact": "Balanced",
                "consequences": "Delay event",
                "risks": ["Coordination effort"],
                "benefits": ["Both possible"]
            })

    return scenarios


def _score_scenarios_differentiated(
    scenarios,
    task_analysis,
    calendar_result
):

    urgency = task_analysis.get("urgency_score", 5)
    has_conflict = calendar_result.get("has_conflict", False)

    task_priority = calendar_result.get("task_priority", "medium")
    event_priority = calendar_result.get("event_priority", "medium")

    scored = []

    for s in scenarios:
        action = s["action"].lower()
        score = 50

        if has_conflict and task_priority == "high" and event_priority == "low":
            if "skip" in action:
                score = 90
            elif "attend" in action:
                score = 20
            else:
                score = 75

        elif "skip" in action:
            score = 70 if urgency >= 7 else 40

        elif "attend" in action:
            score = 30 if urgency >= 7 else 60

        elif "reschedule" in action:
            score = 65

        s["score"] = score
        scored.append(s)

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored


def _force_score_differentiation(scenarios):
    for i in range(1, len(scenarios)):
        if scenarios[i]["score"] >= scenarios[i-1]["score"]:
            scenarios[i]["score"] = scenarios[i-1]["score"] - 5
    return scenarios