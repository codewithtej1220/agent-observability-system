"""Data schema for agent execution traces.

A Trace is the atomic unit the whole pipeline operates on: an ordered
sequence of Steps produced by one agent run, plus metadata used for
evaluation (label, outcome) when available.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Step:
    """A single step (tool call, reasoning step, or final answer) within an agent run."""

    step_id: int
    action_type: str  # "tool_call" | "tool_error" | "final_answer"
    tool_name: Optional[str] = None
    arguments: Dict[str, Any] = field(default_factory=dict)
    output: str = ""
    latency_ms: float = 0.0
    tokens_used: int = 0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Trace:
    """A full agent run: an ordered sequence of steps plus metadata."""

    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task_description: str = ""
    steps: List[Step] = field(default_factory=list)
    label: Optional[str] = None  # "healthy" | "pathological" | None (unknown / real traffic)
    outcome: Optional[str] = None  # "success" | "failure" | None

    def add_step(self, step: Step) -> None:
        self.steps.append(step)

    def total_tokens(self) -> int:
        return sum(s.tokens_used for s in self.steps)

    def total_latency_ms(self) -> float:
        return sum(s.latency_ms for s in self.steps)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "task_description": self.task_description,
            "steps": [s.to_dict() for s in self.steps],
            "label": self.label,
            "outcome": self.outcome,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Trace":
        raw_steps = d.get("steps", [])
        steps = [Step(**s) if not isinstance(s, Step) else s for s in raw_steps]
        return Trace(
            trace_id=d.get("trace_id") or str(uuid.uuid4()),
            task_description=d.get("task_description", ""),
            steps=steps,
            label=d.get("label"),
            outcome=d.get("outcome"),
        )
