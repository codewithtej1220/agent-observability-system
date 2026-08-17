"""Trace -> fixed-size feature vector embedding pipeline.

Combines lightweight text features (hashed n-grams over tool names,
arguments, and outputs) with engineered numeric features describing the
shape of the run (step count, tool diversity, repetition, error rate,
latency, token cost).

Uses scikit-learn's HashingVectorizer rather than a downloaded embedding
model, so the whole pipeline is self-contained and reproducible with no
external model downloads required. Swap in sentence-transformers later for
richer semantic text features if desired.
"""
from __future__ import annotations

from typing import List

import numpy as np
from sklearn.feature_extraction.text import HashingVectorizer
from sklearn.preprocessing import StandardScaler

from agent_harness.trace_schema import Trace

TEXT_EMBED_DIM = 64
NUMERIC_FEATURE_NAMES = [
    "n_steps",
    "unique_tools",
    "tool_diversity",
    "repetition_ratio",
    "error_ratio",
    "total_latency_ms",
    "total_tokens",
    "ends_in_final_answer",
]


def _trace_to_text(trace: Trace) -> str:
    parts: List[str] = []
    for step in trace.steps:
        parts.append(step.action_type)
        if step.tool_name:
            parts.append(step.tool_name)
        parts.append(" ".join(f"{k}={v}" for k, v in step.arguments.items()))
        parts.append(step.output[:200])
    return " ".join(parts)


def _numeric_features(trace: Trace) -> np.ndarray:
    steps = trace.steps
    n_steps = len(steps)
    if n_steps == 0:
        return np.zeros(len(NUMERIC_FEATURE_NAMES), dtype=np.float32)

    tool_names = [s.tool_name for s in steps if s.tool_name]
    unique_tools = len(set(tool_names))
    tool_diversity = unique_tools / max(1, len(tool_names)) if tool_names else 0.0

    seen = set()
    repeated_calls = 0
    for s in steps:
        # Convert arguments to string to make it hashable
        args_str = str(sorted(s.arguments.items())) if s.arguments else ""
        key = (s.tool_name, args_str)
        if key in seen:
            repeated_calls += 1
        seen.add(key)
    repetition_ratio = repeated_calls / n_steps

    error_steps = sum(1 for s in steps if s.action_type == "tool_error" or "ERROR" in s.output)
    error_ratio = error_steps / n_steps

    ends_in_final_answer = 1.0 if steps[-1].action_type == "final_answer" else 0.0


    return np.array(
        [
            n_steps,
            unique_tools,
            tool_diversity,
            repetition_ratio,
            error_ratio,
            trace.total_latency_ms(),
            trace.total_tokens(),
            ends_in_final_answer,
        ],
        dtype=np.float32,
    )


class TraceEmbedder:
    """Fits a scaler over numeric features and combines them with hashed text features."""

    def __init__(self, text_dim: int = TEXT_EMBED_DIM):
        self.text_dim = text_dim
        self._vectorizer = HashingVectorizer(n_features=text_dim, alternate_sign=False, norm="l2")
        self._scaler = StandardScaler()
        self._fitted = False

    def fit(self, traces: List[Trace]) -> "TraceEmbedder":
        numeric = np.stack([_numeric_features(t) for t in traces])
        self._scaler.fit(numeric)
        self._fitted = True
        return self

    def transform(self, traces: List[Trace]) -> np.ndarray:
        if not self._fitted:
            raise RuntimeError("TraceEmbedder must be fit() before transform().")
        text_matrix = self._vectorizer.transform([_trace_to_text(t) for t in traces]).toarray()
        numeric = np.stack([_numeric_features(t) for t in traces])
        numeric_scaled = self._scaler.transform(numeric)
        return np.hstack([text_matrix, numeric_scaled]).astype(np.float32)

    def fit_transform(self, traces: List[Trace]) -> np.ndarray:
        return self.fit(traces).transform(traces)
