"""
Pydantic schemas for request/response validation in DecisionOS.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


# ============================================================
# Request Schemas
# ============================================================

class DecisionRequest(BaseModel):
    """Request schema for decision endpoint."""
    user_id: str = Field(..., description="Unique user identifier")
    message: str = Field(..., description="User's decision request message")


class EventCreate(BaseModel):
    """Schema for creating calendar events."""
    title: str
    description: Optional[str] = None
    start_time: datetime
    end_time: datetime


class EventReschedule(BaseModel):
    """Schema for rescheduling events."""
    event_id: str
    new_start_time: datetime
    new_end_time: datetime


class TaskCreate(BaseModel):
    """Schema for creating tasks."""
    title: str
    description: Optional[str] = None
    priority: Optional[int] = 5
    deadline: Optional[datetime] = None
    estimated_duration: Optional[float] = None


# ============================================================
# Response Schemas
# ============================================================

class PlannerOutput(BaseModel):
    """Output from the Planner Agent."""
    task_type: Optional[str] = None
    task_description: Optional[str] = None
    deadline_raw: Optional[str] = None
    meeting_raw: Optional[str] = None
    constraints: List[str] = Field(default_factory=list)
    context: Optional[str] = None


class TaskAnalysis(BaseModel):
    """Output from the Task Agent."""
    urgency_score: float = Field(ge=0, le=10)
    importance_score: float = Field(ge=0, le=10)
    priority: int = Field(ge=1, le=10)
    estimated_duration: float  # hours
    reasoning: Optional[str] = None


class TimeContext(BaseModel):
    """Output from Time Resolver."""
    current_time: datetime
    meeting_start: Optional[datetime] = None
    meeting_end: Optional[datetime] = None
    deadline: Optional[datetime] = None


class CalendarResult(BaseModel):
    """Output from the Calendar Agent."""
    available_time: float  # hours
    required_time: float  # hours
    buffer_time: float  # hours
    has_conflict: bool
    conflict_reason: Optional[str] = None
    alternatives: List[str] = Field(default_factory=list)


class ScenarioOption(BaseModel):
    """A single scenario option."""
    action: str
    description: str
    outcomes: Dict[str, str] = Field(default_factory=dict)
    score: float = Field(ge=0, le=100)
    risks: List[str] = Field(default_factory=list)
    benefits: List[str] = Field(default_factory=list)


class ScenarioAnalysis(BaseModel):
    """Output from the Scenario Agent."""
    options: List[ScenarioOption] = Field(default_factory=list)
    recommendation: Optional[str] = None


class ActionItem(BaseModel):
    """A single executable action."""
    type: str = Field(..., description="Action type: reschedule_event, cancel_event, create_event, add_task")
    event_id: Optional[str] = None
    event_title: Optional[str] = None
    suggested_time: Optional[str] = None
    params: Dict[str, Any] = Field(default_factory=dict)


class ExecuteActionRequest(BaseModel):
    """Request to execute an action via MCP."""
    user_id: str
    action_type: str
    event_id: Optional[str] = None
    params: Dict[str, Any] = Field(default_factory=dict)


class HumanScenario(BaseModel):
    """Human-friendly scenario format."""
    option: str = Field(..., description="Short action name")
    outcome: str = Field(..., description="What will happen")
    risk: str = Field(..., description="What you might lose")
    score: int = Field(ge=0, le=100)
    recommended: bool = False


class FinalDecision(BaseModel):
    """Output from the Decision Engine."""
    action: str = Field(..., description="The recommended action")
    decision_text: str = Field(default="", description="Human-readable decision statement")
    confidence: float = Field(ge=0, le=1, description="Confidence score 0-1")
    reasoning: str = Field(..., description="Explanation for the decision")
    next_steps: List[str] = Field(default_factory=list)
    mcp_actions: List[Dict[str, Any]] = Field(default_factory=list)
    executable_actions: List[ActionItem] = Field(default_factory=list)
    conflict_type: Optional[str] = Field(None, description="time_conflict | priority_conflict | none")
    based_on_history: bool = Field(default=False)


class DecisionResponse(BaseModel):
    """Complete response from the decision pipeline."""
    success: bool
    user_id: str
    input_message: str
    planner_output: Optional[PlannerOutput] = None
    task_analysis: Optional[TaskAnalysis] = None
    time_context: Optional[TimeContext] = None
    calendar_result: Optional[CalendarResult] = None
    scenario_analysis: Optional[ScenarioAnalysis] = None
    final_decision: Optional[FinalDecision] = None
    mcp_results: List[Dict[str, Any]] = Field(default_factory=list)
    error: Optional[str] = None


class SSEEvent(BaseModel):
    """Server-Sent Event structure."""
    event: str
    data: Dict[str, Any]
