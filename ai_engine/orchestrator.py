"""
Orchestrator for DecisionOS.
Coordinates all agents in a simplified, tight pipeline with STRICT validation.
"""

import json
from datetime import datetime
from typing import AsyncGenerator, Dict, Any

from dotenv import load_dotenv
load_dotenv()  # load .env for local dev; no-op in Cloud Run (uses Secret Manager)

from sqlalchemy.orm import Session

from ai_engine.config.defaults import (
    apply_defaults,
    URGENCY_THRESHOLD_FOR_SCENARIOS
)
from ai_engine.utils.time_resolver import resolve_time_context
from ai_engine.utils.helpers import format_sse_event, DateTimeEncoder
from ai_engine.agents.planner_agent import run_planner_agent
from ai_engine.agents.task_agent import run_task_agent
from ai_engine.agents.calendar_agent import run_calendar_agent
from ai_engine.agents.scenario_agent import run_scenario_agent
from ai_engine.agents.decision_engine import run_decision_engine, make_direct_decision, DecisionEngineError
from backend.tools.mcp_tools import MCPTools
from backend.db.database import Decision, get_or_create_user   # ← real implementations


class ValidationError(Exception):
    """Raised when pipeline validation fails."""
    pass


def _validate_planner_output(planner_output: Dict[str, Any]) -> None:
    if not planner_output:
        raise ValidationError("Planner agent returned no output - cannot proceed")
    if not planner_output.get("task_description"):
        raise ValidationError("Planner failed to extract task description - cannot proceed")


def _validate_calendar_output(calendar_result: Dict[str, Any]) -> None:
    if not calendar_result:
        raise ValidationError("Calendar agent returned no output - cannot proceed")
    if calendar_result.get("available_time") is None:
        raise ValidationError("Calendar agent did not compute available_time - cannot proceed")


def _validate_scenarios(scenario_analysis: Dict[str, Any]) -> None:
    if not scenario_analysis:
        raise ValidationError("Scenario agent returned no output - cannot proceed")
    options = scenario_analysis.get("options", [])
    if len(options) < 3:
        raise ValidationError(f"Scenario agent returned {len(options)} scenarios (need 3) - cannot proceed")
    scores = [opt.get("score", 0) for opt in options]
    if len(set(scores)) == 1:
        raise ValidationError(f"All scenarios have same score ({scores[0]}) - cannot differentiate")


async def stream_decision(
    db: Session,
    user_id: str,
    message: str
) -> AsyncGenerator[str, None]:
    """
    Main decision pipeline with SSE streaming.

    Pipeline:
    1. Planner Agent      — extract structured data from message
    2. Apply Defaults     — fill missing fields
    3. Time Resolver      — parse time context
    4. Task Agent         — calculate urgency / importance
    5. Calendar Agent     — detect conflicts from Google Calendar or DB
    6. IF conflict OR urgency >= threshold:
         Scenario Agent + Decision Engine
       ELSE:
         Direct Decision
    7. MCP Tool Execution — reschedule / cancel calendar events
    8. Store in DB
    9. Final SSE response
    """
    pipeline_results = {
        "user_id": user_id,
        "input_message": message,
        "planner_output": None,
        "task_analysis": None,
        "time_context": None,
        "calendar_result": None,
        "scenario_analysis": None,
        "final_decision": None,
        "mcp_results": []
    }

    try:
        # ── Step 1: Planner ──────────────────────────────────────
        yield format_sse_event("agent_start", {
            "agent": "planner",
            "status": "running",
            "message": "Extracting task information..."
        })

        planner_output = await run_planner_agent(message)
        pipeline_results["planner_output"] = planner_output

        try:
            _validate_planner_output(planner_output)
        except ValidationError as ve:
            yield format_sse_event("error", {"success": False, "error": str(ve), "stage": "planner_validation"})
            return

        yield format_sse_event("agent_complete", {"agent": "planner", "status": "complete", "data": planner_output})

        # ── Step 2: Defaults ─────────────────────────────────────
        yield format_sse_event("processing", {"step": "defaults", "message": "Applying system defaults..."})
        extracted_with_defaults = apply_defaults(planner_output)
        yield format_sse_event("processing_complete", {
            "step": "defaults",
            "data": {
                "estimated_duration": extracted_with_defaults.get("estimated_duration"),
                "buffer_time": extracted_with_defaults.get("buffer_time")
            }
        })

        # ── Step 3: Time Resolver ────────────────────────────────
        yield format_sse_event("processing", {"step": "time_resolver", "message": "Resolving time context..."})
        time_context = resolve_time_context(message)
        pipeline_results["time_context"] = _serialize_time_context(time_context)
        yield format_sse_event("processing_complete", {"step": "time_resolver", "data": pipeline_results["time_context"]})

        # ── Step 4: Task Agent ───────────────────────────────────
        yield format_sse_event("agent_start", {"agent": "task", "status": "running", "message": "Analyzing task priority..."})
        task_analysis = run_task_agent(extracted_with_defaults, time_context)
        pipeline_results["task_analysis"] = task_analysis
        yield format_sse_event("agent_complete", {"agent": "task", "status": "complete", "data": task_analysis})

        # ── Step 5: Calendar Agent ───────────────────────────────
        yield format_sse_event("agent_start", {"agent": "calendar", "status": "running", "message": "Checking calendar conflicts..."})

        calendar_result = run_calendar_agent(
            db=db,
            user_id=user_id,
            time_context=time_context,
            task_analysis=task_analysis,
            extracted_data=extracted_with_defaults
        )
        pipeline_results["calendar_result"] = _serialize_calendar_result(calendar_result)

        try:
            _validate_calendar_output(calendar_result)
        except ValidationError as ve:
            yield format_sse_event("error", {"success": False, "error": str(ve), "stage": "calendar_validation"})
            return

        yield format_sse_event("agent_complete", {
            "agent": "calendar",
            "status": "complete",
            "data": pipeline_results["calendar_result"]
        })

        # ── Step 6: Decision Branch ──────────────────────────────
        has_conflict = calendar_result.get("has_conflict", False)
        urgency = task_analysis.get("urgency_score", 5)

        if has_conflict or urgency >= URGENCY_THRESHOLD_FOR_SCENARIOS:
            yield format_sse_event("agent_start", {
                "agent": "scenario",
                "status": "running",
                "message": "Simulating decision scenarios..."
            })

            scenario_analysis = await run_scenario_agent(
                extracted_with_defaults,
                task_analysis,
                calendar_result,
                time_context
            )
            pipeline_results["scenario_analysis"] = scenario_analysis

            try:
                _validate_scenarios(scenario_analysis)
            except ValidationError as ve:
                yield format_sse_event("error", {"success": False, "error": str(ve), "stage": "scenario_validation"})
                return

            yield format_sse_event("agent_complete", {"agent": "scenario", "status": "complete", "data": scenario_analysis})

            yield format_sse_event("agent_start", {
                "agent": "decision_engine",
                "status": "running",
                "message": "Synthesizing final decision..."
            })

            try:
                final_decision = await run_decision_engine(
                    extracted_with_defaults,
                    task_analysis,
                    calendar_result,
                    scenario_analysis,
                    time_context
                )
            except DecisionEngineError as de:
                yield format_sse_event("error", {"success": False, "error": str(de), "stage": "decision_engine"})
                return

            pipeline_results["final_decision"] = final_decision
            yield format_sse_event("agent_complete", {"agent": "decision_engine", "status": "complete", "data": final_decision})

        else:
            yield format_sse_event("processing", {
                "step": "direct_decision",
                "message": "No conflict detected, making direct decision..."
            })

            final_decision = await make_direct_decision(
                extracted_with_defaults,
                task_analysis,
                calendar_result,
                time_context
            )
            pipeline_results["final_decision"] = final_decision
            pipeline_results["scenario_analysis"] = None
            yield format_sse_event("processing_complete", {"step": "direct_decision", "data": final_decision})

        # ── Step 7: MCP Actions ──────────────────────────────────
        mcp_actions = final_decision.get("mcp_actions", [])

        if mcp_actions:
            yield format_sse_event("mcp_start", {
                "message": f"Executing {len(mcp_actions)} action(s)...",
                "actions": [a.get("tool") for a in mcp_actions]
            })

            mcp_tools = MCPTools(db, user_id)
            mcp_results = []

            for action in mcp_actions:
                result = mcp_tools.execute_action(action)
                mcp_results.append(result)
                yield format_sse_event("mcp_action", {"tool": action.get("tool"), "result": result})

            pipeline_results["mcp_results"] = mcp_results
            yield format_sse_event("mcp_complete", {"message": "All actions executed", "results": mcp_results})

        # ── Step 8: Store Decision ───────────────────────────────
        yield format_sse_event("processing", {"step": "database", "message": "Saving decision record..."})

        decision_record = _store_decision(db, user_id, pipeline_results)

        yield format_sse_event("processing_complete", {
            "step": "database",
            "decision_id": decision_record.id if decision_record else None
        })

        # ── Step 9: Final Response ───────────────────────────────
        yield format_sse_event("complete", {
            "success": True,
            "decision": final_decision,
            "summary": _generate_summary(pipeline_results)
        })

    except Exception as e:
        yield format_sse_event("error", {"success": False, "error": str(e), "stage": "pipeline"})


# ─────────────────────────────────────────────
# SERIALIZATION HELPERS
# ─────────────────────────────────────────────

def _serialize_time_context(time_context: Dict[str, Any]) -> Dict[str, Any]:
    serialized = {}
    for key, value in time_context.items():
        serialized[key] = value.isoformat() if isinstance(value, datetime) else value
    return serialized


def _serialize_calendar_result(calendar_result: Dict[str, Any]) -> Dict[str, Any]:
    def serialize_value(val):
        if isinstance(val, datetime):
            return val.isoformat()
        elif isinstance(val, list):
            return [serialize_value(v) for v in val]
        elif isinstance(val, dict):
            return {k: serialize_value(v) for k, v in val.items()}
        return val
    return {k: serialize_value(v) for k, v in calendar_result.items()}


def _store_decision(
    db: Session,
    user_id: str,
    pipeline_results: Dict[str, Any]
) -> Decision:
    """Persist decision to database. Skips gracefully if DB is None (dev mode)."""
    if db is None:
        # No DB configured — skip storage silently
        class _FakeDecision:
            id = None
        return _FakeDecision()

    try:
        user = get_or_create_user(db, user_id)
        final_decision = pipeline_results.get("final_decision", {})

        decision = Decision(
            user_id=user.id,
            input_message=pipeline_results.get("input_message", ""),
            extracted_data=json.dumps(pipeline_results.get("planner_output"), cls=DateTimeEncoder),
            task_analysis=json.dumps(pipeline_results.get("task_analysis"), cls=DateTimeEncoder),
            calendar_result=json.dumps(pipeline_results.get("calendar_result"), cls=DateTimeEncoder),
            scenarios=json.dumps(pipeline_results.get("scenario_analysis"), cls=DateTimeEncoder),
            final_decision=json.dumps(final_decision, cls=DateTimeEncoder),
            action_taken=final_decision.get("action", "unknown"),
            confidence_score=final_decision.get("confidence", 0)
        )

        db.add(decision)
        db.commit()
        db.refresh(decision)
        return decision

    except Exception as e:
        print(f"[Orchestrator] DB store failed: {e}")
        class _FakeDecision:
            id = None
        return _FakeDecision()


def _generate_summary(pipeline_results: Dict[str, Any]) -> Dict[str, Any]:
    task_analysis   = pipeline_results.get("task_analysis", {})
    calendar_result = pipeline_results.get("calendar_result", {})
    final_decision  = pipeline_results.get("final_decision", {})

    return {
        "task_priority":      task_analysis.get("priority", "N/A"),
        "urgency":            task_analysis.get("urgency_score", "N/A"),
        "importance":         task_analysis.get("importance_score", "N/A"),
        "has_conflict":       calendar_result.get("has_conflict", False),
        "recommended_action": final_decision.get("action", "unknown"),
        "confidence":         final_decision.get("confidence", 0),
        "next_steps":         final_decision.get("next_steps", [])
    }