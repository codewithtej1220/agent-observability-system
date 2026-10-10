"""Deterministic, explainable failure detectors.

These run first, on every step, and give the system two things the learned
models cannot: exact guarantees for unambiguous cases (a call to a tool the
agent does not have is a hallucination, full stop) and human-readable
evidence pointing at the steps that triggered them.

Each detector returns a Signal with a severity in [0, 1]. The learned models
consume the same features, so detectors are not the only line of defense --
they are the explainable one.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List

from .features import RunProfile


@dataclass
class Signal:
    failure_type: str
    detector: str
    severity: float
    message: str
    evidence_steps: List[int] = field(default_factory=list)

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["severity"] = round(self.severity, 3)
        return d


def _clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def detect_loop(p: RunProfile) -> List[Signal]:
    f = p.features
    out: List[Signal] = []

    streak = int(f["max_identical_streak"])
    if streak >= 3:
        out.append(Signal(
            "loop", "identical_calls", _clip((streak - 1) / 4),
            f"Same tool called with identical arguments {streak} times in a row",
            p.identical_streak_steps,
        ))

    period = p.cycle_period
    if period >= 2 and p.cycle_steps:
        reps = len(p.cycle_steps) / period
        if reps >= 3 and f["recent_novelty"] < 0.3:
            out.append(Signal(
                "loop", "tool_cycle", _clip(0.3 * reps - 0.3),
                f"Tool sequence repeats a {period}-step cycle {reps:.0f} times without new information",
                p.cycle_steps,
            ))

    near = len(p.near_dup_steps)
    if near >= 2 and f["recent_novelty"] < 0.35:
        out.append(Signal(
            "loop", "near_duplicate_calls", _clip(0.25 * near),
            f"{near} calls only slightly rephrase the previous call's arguments",
            p.near_dup_steps,
        ))
    return out


def detect_thrashing(p: RunProfile) -> List[Signal]:
    f = p.features
    steps = p.run.steps
    if f["n_tool_calls"] < 5:
        return []
    window = steps[-8:]
    tools = [s.tool_name for s in window if s.type == "tool_call"]
    if len(tools) < 4:
        return []
    switch = sum(1 for a, b in zip(tools, tools[1:]) if a != b) / (len(tools) - 1)
    err = sum(1 for s in window if s.is_error) / len(window)
    stuck = 1.0 - f["recent_novelty"]
    if switch < 0.6 or (err < 0.3 and stuck < 0.75):
        return []
    severity = _clip(0.9 * (switch - 0.4) + 0.8 * err + 0.4 * (stuck - 0.5))
    if severity < 0.3:
        return []
    return [Signal(
        "tool_thrashing", "switching_without_progress", severity,
        f"Switching tools on {switch:.0%} of recent calls with {err:.0%} errors and little new information",
        [s.index for s in window if s.type == "tool_call"],
    )]


def detect_hallucinated_tools(p: RunProfile) -> List[Signal]:
    if not p.unknown_steps:
        return []
    names = sorted({p.run.steps[i].tool_name or "?" for i in p.unknown_steps})
    count = len(p.unknown_steps)
    severity = {1: 0.65, 2: 0.85}.get(count, 1.0)
    return [Signal(
        "hallucinated_tool", "unregistered_tool", severity,
        f"Called tool(s) not available to this agent: {', '.join(names)}",
        list(p.unknown_steps),
    )]


def detect_token_waste(p: RunProfile) -> List[Signal]:
    f = p.features
    steps = p.run.steps
    rel = f["tokens_vs_baseline"]
    verbose = [s.index for s in steps if s.type == "llm" and s.output_tokens >= 600 and p.novelty[s.index] < 0.35]
    out: List[Signal] = []

    if rel >= 1.8 and f["recent_novelty"] < 0.35 and not p.run.has_final_answer:
        severity = _clip((rel - 1.3) / 2.0) * _clip((0.45 - f["recent_novelty"]) / 0.3)
        if severity >= 0.25:
            out.append(Signal(
                "token_waste", "spend_without_progress", severity,
                f"Spent {rel:.1f}x this agent's typical tokens while recent steps add little new information",
                [s.index for s in steps[-4:]],
            ))
    if len(verbose) >= 2:
        out.append(Signal(
            "token_waste", "verbose_low_information", _clip(0.25 * len(verbose)),
            f"{len(verbose)} long reasoning steps that mostly restate earlier content",
            verbose,
        ))
    return out


ALL_DETECTORS = [detect_loop, detect_thrashing, detect_hallucinated_tools, detect_token_waste]


def run_detectors(p: RunProfile) -> List[Signal]:
    signals: List[Signal] = []
    for det in ALL_DETECTORS:
        signals.extend(det(p))
    signals.sort(key=lambda s: s.severity, reverse=True)
    return signals


def max_severity_by_type(signals: List[Signal]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for s in signals:
        out[s.failure_type] = max(out.get(s.failure_type, 0.0), s.severity)
    return out
