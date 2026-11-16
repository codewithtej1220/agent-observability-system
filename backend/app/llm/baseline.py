"""Per-model statistical baseline: flag responses that are unusual for the model.

For each (workspace, provider, model) the recent history of successful calls
gives a median and MAD for output length, latency and prompt relevance. A
response whose robust z-score is beyond THRESHOLD on any of them gets an
informational "Unusual for this model" check. Catches silent changes that no
rule describes: a model that suddenly answers in one line, rambles, slows
down, or drifts off topic.

Baselines are cached for a few minutes, so the check costs one query per
model per refresh, not one per call.
"""
from __future__ import annotations

import statistics
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from ..orm_llm import LLMCall
from .checks import CheckResult

MIN_SAMPLES = 50
WINDOW = 500
THRESHOLD = 4.0
TTL_S = 300
MAD_SCALE = 1.4826  # MAD -> standard deviation for normal data


@dataclass
class Stat:
    median: float
    scale: float

    def z(self, x: float) -> float:
        return (x - self.median) / self.scale if self.scale > 0 else 0.0


def _stat(values: List[float], floor: float) -> Optional[Stat]:
    if len(values) < MIN_SAMPLES:
        return None
    med = statistics.median(values)
    mad = statistics.median(abs(v - med) for v in values) * MAD_SCALE
    return Stat(med, max(mad, floor))


_cache: Dict[Tuple[int, str, str], Tuple[float, Dict[str, Stat]]] = {}


def baseline(db: Session, ws_id: int, provider: str, model: str) -> Dict[str, Stat]:
    key = (ws_id, provider, model)
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < TTL_S:
        return hit[1]
    rows = (db.query(LLMCall.output_tokens, LLMCall.latency_ms, LLMCall.relevance)
            .filter(LLMCall.workspace_id == ws_id, LLMCall.provider == provider, LLMCall.model == model,
                    LLMCall.status_code < 400, LLMCall.source == "gateway")
            .order_by(LLMCall.created_at.desc()).limit(WINDOW).all())
    stats: Dict[str, Stat] = {}
    for name, idx, floor in (("output_tokens", 0, 5.0), ("latency_ms", 1, 100.0), ("relevance", 2, 0.05)):
        s = _stat([float(r[idx]) for r in rows if r[idx] is not None], floor)
        if s:
            stats[name] = s
    _cache[key] = (time.monotonic(), stats)
    return stats


LABELS = {"output_tokens": ("longer", "shorter", "answer length", "{:.0f} tokens"),
          "latency_ms": ("slower", "faster", "latency", "{:.0f} ms"),
          "relevance": ("more on-topic", "less on-topic", "relevance to the prompt", "{:.2f}")}


def check(db: Session, ws_id: int, provider: str, model: str, values: Dict[str, Optional[float]]) -> Optional[CheckResult]:
    """An "Unusual for this model" result, or None when nothing stands out (or no baseline yet)."""
    if not model:
        return None
    stats = baseline(db, ws_id, provider, model)
    notes = []
    for name, x in values.items():
        st = stats.get(name)
        if st is None or x is None:
            continue
        z = st.z(float(x))
        if name == "latency_ms" and z < 0:
            continue  # faster than usual is not a problem
        if abs(z) >= THRESHOLD:
            up, down, what, fmt = LABELS[name]
            notes.append(f"{what} {fmt.format(x)} vs typical {fmt.format(st.median)} ({up if z > 0 else down})")
    if not notes:
        return None
    return CheckResult("model_anomaly", "model_anomaly", "Unusual for this model", False, "info",
                       "; ".join(notes), "builtin")
