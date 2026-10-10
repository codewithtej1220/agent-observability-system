"""Framework-agnostic representation of an agent run.

A Run is an ordered list of Steps. Each step is one iteration of the agent
loop: the model decides on an action (call a tool, think, or answer), and
the result of that action is recorded. Everything downstream (features,
detectors, models, policy) operates on this structure, so any agent
framework can be supported by mapping its events onto it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

STEP_TYPES = ("tool_call", "llm", "final_answer")


@dataclass
class Step:
    index: int
    type: str  # one of STEP_TYPES
    tool_name: Optional[str] = None
    arguments: Dict[str, Any] = field(default_factory=dict)
    output: str = ""
    status: str = "ok"  # "ok" | "error"
    latency_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    timestamp: Optional[float] = None

    @property
    def tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def is_error(self) -> bool:
        return self.status == "error"


@dataclass
class Run:
    run_id: str
    agent_id: str
    steps: List[Step] = field(default_factory=list)
    task: str = ""
    model: str = ""
    # Tools the agent is allowed to call. None means "unknown" and the
    # pipeline falls back to the tool vocabulary learned from history.
    registered_tools: Optional[List[str]] = None
    # Ground truth from the simulator (never used at inference time).
    source_label: Optional[str] = None
    failure_onset: Optional[int] = None

    def prefix(self, n: int) -> "Run":
        return Run(
            run_id=self.run_id,
            agent_id=self.agent_id,
            steps=self.steps[:n],
            task=self.task,
            model=self.model,
            registered_tools=self.registered_tools,
            source_label=self.source_label,
            failure_onset=self.failure_onset,
        )

    @property
    def total_tokens(self) -> int:
        return sum(s.tokens for s in self.steps)

    @property
    def has_final_answer(self) -> bool:
        return bool(self.steps) and self.steps[-1].type == "final_answer"
