"""Request/response models for the public API."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from ml import CLASSES
from ml.bandit import ACTIONS

StepType = Literal["tool_call", "llm", "final_answer"]


class StepIn(BaseModel):
    type: StepType
    tool_name: Optional[str] = None
    arguments: Dict[str, Any] = Field(default_factory=dict)
    output: str = ""
    status: Literal["ok", "error"] = "ok"
    latency_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    timestamp: Optional[datetime] = None


class AgentIn(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_.\-]{1,64}$")
    name: Optional[str] = None
    description: str = ""
    model: str = ""
    framework: str = ""
    registered_tools: Optional[List[str]] = None


class RunStartIn(BaseModel):
    run_id: Optional[str] = None
    agent_id: str
    task: str = ""
    model: str = ""
    registered_tools: Optional[List[str]] = None
    started_at: Optional[datetime] = None


class RunIn(RunStartIn):
    steps: List[StepIn]
    # Optional ground truth, used only by the simulator for evaluation.
    source_label: Optional[str] = None
    failure_onset: Optional[int] = None


class FeedbackIn(BaseModel):
    label: str = Field(description=f"True condition of the run: one of {CLASSES}")
    action_taken: Optional[str] = Field(None, description=f"Intervention applied; one of {ACTIONS}. Defaults to the recommendation.")
    resolved: bool = Field(description="Did the run ultimately achieve its goal?")
    notes: str = ""
    reviewer: str = ""


class AssessmentOut(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    run_id: str
    step_count: int
    risk_score: float
    severity: str
    failure_type: Optional[str]
    probabilities: Dict[str, float]
    signals: List[Dict[str, Any]]
    recommended_action: str
    action_label: str
    action_reason: str
    first_flag_step: Optional[int]
    model_version: str
