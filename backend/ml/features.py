"""Behavioral feature extraction.

Silent failures are behavioral, not textual: an agent stuck in a loop and a
healthy agent may produce similar-looking text. So instead of embedding raw
text, we describe the *shape* of a run -- repetition, cycles, tool
switching, errors, information gain per step, and token spend relative to
that agent's own baseline.

All features are computable on any prefix of a run, which is what makes
mid-run (early) detection possible.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Dict, Iterable, List, Optional, Sequence, Set

import numpy as np

from .schema import Run

FEATURE_NAMES = [
    "n_steps",
    "n_tool_calls",
    "unique_tools",
    "tool_diversity",
    "max_identical_streak",
    "duplicate_call_ratio",
    "near_duplicate_ratio",
    "tail_cycle_ratio",
    "tail_cycle_period",
    "switch_rate",
    "transition_entropy",
    "error_ratio",
    "max_error_streak",
    "recent_error_ratio",
    "unknown_tool_ratio",
    "unknown_tool_count",
    "output_novelty",
    "recent_novelty",
    "stall_steps",
    "log_total_tokens",
    "log_tokens_per_step",
    "output_token_ratio",
    "token_efficiency",
    "llm_step_ratio",
    "log_llm_output_tokens",
    "has_final_answer",
    "log_mean_latency",
    "tokens_vs_baseline",
    "steps_vs_baseline",
]

FEATURE_DESCRIPTIONS = {
    "n_steps": "Number of steps so far",
    "n_tool_calls": "Number of tool calls",
    "unique_tools": "Distinct tools used",
    "tool_diversity": "Distinct tools / tool calls",
    "max_identical_streak": "Longest run of identical tool+argument calls",
    "duplicate_call_ratio": "Share of calls that exactly repeat an earlier call",
    "near_duplicate_ratio": "Share of calls nearly identical to the previous call",
    "tail_cycle_ratio": "Share of recent calls that form a repeating cycle",
    "tail_cycle_period": "Period of the repeating cycle at the end of the run",
    "switch_rate": "How often consecutive calls switch tool",
    "transition_entropy": "Unpredictability of tool-to-tool transitions",
    "error_ratio": "Share of steps that errored",
    "max_error_streak": "Longest run of consecutive errors",
    "recent_error_ratio": "Error share over the last 5 steps",
    "unknown_tool_ratio": "Share of calls to tools the agent does not have",
    "unknown_tool_count": "Calls to tools the agent does not have",
    "output_novelty": "Average share of new information (unseen word pairs) per step",
    "recent_novelty": "New information over the last 4 steps",
    "stall_steps": "Steps since output last added new information",
    "log_total_tokens": "Total tokens (log)",
    "log_tokens_per_step": "Tokens per step (log)",
    "output_token_ratio": "Output tokens / total tokens",
    "token_efficiency": "New word pairs produced per 100 tokens spent",
    "llm_step_ratio": "Share of pure reasoning steps (no tool)",
    "log_llm_output_tokens": "Average output tokens of reasoning steps (log)",
    "has_final_answer": "Run ended with a final answer",
    "log_mean_latency": "Mean step latency (log ms)",
    "tokens_vs_baseline": "Tokens relative to this agent's typical run",
    "steps_vs_baseline": "Steps relative to this agent's typical run",
}

_WORD = re.compile(r"[a-z0-9_]+")
NOVELTY_THRESHOLD = 0.3


def _words(text: str) -> List[str]:
    return _WORD.findall(text.lower())


def _bigrams(text: str) -> Set[str]:
    w = _words(text)
    if len(w) < 2:
        return set(w)
    return {f"{a} {b}" for a, b in zip(w, w[1:])}


def _signature(tool: Optional[str], args: Dict) -> str:
    try:
        arg_str = json.dumps(args, sort_keys=True, default=str)
    except TypeError:
        arg_str = str(args)
    return f"{tool}|{arg_str}"


def _arg_text(args: Dict) -> str:
    return " ".join(f"{k}={v}" for k, v in sorted(args.items(), key=lambda kv: kv[0]))


@dataclass
class Baseline:
    """Typical behavior of one agent, learned from its low-risk history."""

    median_tokens: float = 4000.0
    median_steps: float = 6.0

    def to_dict(self) -> Dict[str, float]:
        return {"median_tokens": self.median_tokens, "median_steps": self.median_steps}


@dataclass
class RunProfile:
    """Intermediate per-step structures shared by features and detectors."""

    run: Run
    tool_steps: List[int] = field(default_factory=list)  # step indexes of tool calls
    tool_seq: List[str] = field(default_factory=list)
    signatures: List[str] = field(default_factory=list)
    novelty: List[float] = field(default_factory=list)  # per step
    new_words: List[int] = field(default_factory=list)  # per step
    unknown_steps: List[int] = field(default_factory=list)
    identical_streak_steps: List[int] = field(default_factory=list)
    near_dup_steps: List[int] = field(default_factory=list)
    cycle_steps: List[int] = field(default_factory=list)
    cycle_period: int = 0
    features: Dict[str, float] = field(default_factory=dict)


def _tail_cycle(seq: Sequence[str], max_period: int = 3) -> tuple[int, int]:
    """Longest suffix of `seq` that repeats with a period <= max_period.

    Returns (length_of_repeating_suffix, period). A suffix only counts if it
    contains at least two full repetitions of the period.
    """
    best_len, best_p = 0, 0
    n = len(seq)
    for p in range(1, max_period + 1):
        if n < 2 * p:
            continue
        length = p
        i = n - 1 - p
        while i >= 0 and seq[i] == seq[i + p]:
            length += 1
            i -= 1
        # For p > 1, require the cycle to actually involve p distinct items,
        # otherwise it is the same as a shorter period.
        if p > 1 and len(set(seq[n - p:])) < p:
            continue
        if length >= 2 * p and length > best_len:
            best_len, best_p = length, p
    return best_len, best_p


def profile_run(
    run: Run,
    known_tools: Optional[Iterable[str]] = None,
    baseline: Optional[Baseline] = None,
) -> RunProfile:
    baseline = baseline or Baseline()
    allowed: Optional[Set[str]] = None
    if run.registered_tools:
        allowed = set(run.registered_tools)
    elif known_tools is not None:
        allowed = set(known_tools)

    prof = RunProfile(run=run)
    steps = run.steps
    n = len(steps)

    seen_words: Set[str] = set()
    seen_sigs: Set[str] = set()
    duplicate_calls = 0
    streak, max_streak = 0, 0
    streak_start = 0
    best_streak_range = (0, 0)
    err_streak, max_err_streak = 0, 0
    prev_tool_step = None

    for s in steps:
        # Novelty over word bigrams: robust to common-word reuse, while a
        # repeated or restated output contributes almost no unseen bigrams.
        grams = _bigrams(s.output)
        if grams:
            fresh = [g for g in grams if g not in seen_words]
            nov = len(fresh) / len(grams)
            prof.new_words.append(len(fresh))
            seen_words.update(grams)
        else:
            nov = 0.0
            prof.new_words.append(0)
        prof.novelty.append(nov)

        if s.is_error:
            err_streak += 1
            max_err_streak = max(max_err_streak, err_streak)
        else:
            err_streak = 0

        if s.type != "tool_call":
            continue

        sig = _signature(s.tool_name, s.arguments)
        prof.tool_steps.append(s.index)
        prof.tool_seq.append(s.tool_name or "?")
        prof.signatures.append(sig)
        if sig in seen_sigs:
            duplicate_calls += 1
        seen_sigs.add(sig)

        if allowed is not None and s.tool_name not in allowed:
            prof.unknown_steps.append(s.index)

        if prev_tool_step is not None and prof.signatures[-2] == sig:
            streak += 1
        else:
            streak = 1
            streak_start = s.index
        if streak > max_streak:
            max_streak = streak
            best_streak_range = (streak_start, s.index)

        if prev_tool_step is not None:
            prev = steps[prev_tool_step]
            if prev.tool_name == s.tool_name and prof.signatures[-2] != sig:
                sim = SequenceMatcher(None, _arg_text(prev.arguments), _arg_text(s.arguments)).ratio()
                if sim >= 0.8:
                    prof.near_dup_steps.append(s.index)
        prev_tool_step = s.index

    if max_streak >= 2:
        lo, hi = best_streak_range
        prof.identical_streak_steps = [i for i in prof.tool_steps if lo <= i <= hi]

    n_calls = len(prof.tool_seq)
    cyc_len, cyc_p = _tail_cycle(prof.tool_seq)
    # A period-1 "cycle" over tool names is only suspicious when args are
    # also (near-)identical; legitimate pagination is handled by novelty.
    prof.cycle_period = cyc_p
    if cyc_len:
        prof.cycle_steps = prof.tool_steps[-cyc_len:]

    switches = sum(1 for a, b in zip(prof.tool_seq, prof.tool_seq[1:]) if a != b)
    bigrams = Counter(zip(prof.tool_seq, prof.tool_seq[1:]))
    if bigrams:
        total = sum(bigrams.values())
        ent = -sum((c / total) * math.log(c / total) for c in bigrams.values())
        max_ent = math.log(len(bigrams)) if len(bigrams) > 1 else 1.0
        trans_entropy = ent / max_ent if max_ent > 0 else 0.0
    else:
        trans_entropy = 0.0

    errors = sum(1 for s in steps if s.is_error)
    recent = steps[-5:]
    recent_err = sum(1 for s in recent if s.is_error) / max(1, len(recent))

    stall = 0
    for nov in reversed(prof.novelty):
        if nov > NOVELTY_THRESHOLD:
            break
        stall += 1

    total_tokens = sum(s.tokens for s in steps)
    out_tokens = sum(s.output_tokens for s in steps)
    llm_steps = [s for s in steps if s.type == "llm"]
    new_words_total = sum(prof.new_words)
    mean_latency = float(np.mean([s.latency_ms for s in steps])) if steps else 0.0

    f = {
        "n_steps": float(n),
        "n_tool_calls": float(n_calls),
        "unique_tools": float(len(set(prof.tool_seq))),
        "tool_diversity": len(set(prof.tool_seq)) / n_calls if n_calls else 0.0,
        "max_identical_streak": float(max_streak),
        "duplicate_call_ratio": duplicate_calls / n_calls if n_calls else 0.0,
        "near_duplicate_ratio": len(prof.near_dup_steps) / n_calls if n_calls else 0.0,
        "tail_cycle_ratio": cyc_len / n_calls if n_calls else 0.0,
        "tail_cycle_period": float(cyc_p),
        "switch_rate": switches / (n_calls - 1) if n_calls > 1 else 0.0,
        "transition_entropy": trans_entropy,
        "error_ratio": errors / n if n else 0.0,
        "max_error_streak": float(max_err_streak),
        "recent_error_ratio": recent_err,
        "unknown_tool_ratio": len(prof.unknown_steps) / n_calls if n_calls else 0.0,
        "unknown_tool_count": float(len(prof.unknown_steps)),
        "output_novelty": float(np.mean(prof.novelty)) if prof.novelty else 0.0,
        "recent_novelty": float(np.mean(prof.novelty[-4:])) if prof.novelty else 0.0,
        "stall_steps": float(stall),
        "log_total_tokens": math.log1p(total_tokens),
        "log_tokens_per_step": math.log1p(total_tokens / n) if n else 0.0,
        "output_token_ratio": out_tokens / total_tokens if total_tokens else 0.0,
        "token_efficiency": 100.0 * new_words_total / total_tokens if total_tokens else 0.0,
        "llm_step_ratio": len(llm_steps) / n if n else 0.0,
        "log_llm_output_tokens": math.log1p(np.mean([s.output_tokens for s in llm_steps])) if llm_steps else 0.0,
        "has_final_answer": 1.0 if run.has_final_answer else 0.0,
        "log_mean_latency": math.log1p(mean_latency),
        "tokens_vs_baseline": total_tokens / max(1.0, baseline.median_tokens),
        "steps_vs_baseline": n / max(1.0, baseline.median_steps),
    }
    prof.features = f
    return prof


def feature_vector(prof: RunProfile) -> np.ndarray:
    return np.array([prof.features[name] for name in FEATURE_NAMES], dtype=np.float64)


def featurize(
    runs: Sequence[Run],
    known_tools: Optional[Dict[str, Set[str]]] = None,
    baselines: Optional[Dict[str, Baseline]] = None,
) -> np.ndarray:
    known_tools = known_tools or {}
    baselines = baselines or {}
    rows = [
        feature_vector(profile_run(r, known_tools.get(r.agent_id), baselines.get(r.agent_id)))
        for r in runs
    ]
    return np.vstack(rows) if rows else np.zeros((0, len(FEATURE_NAMES)))
