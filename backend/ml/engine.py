"""Detection engine: fuses rules, unsupervised novelty, and the supervised
classifier into one risk score, a failure type, and evidence.

    run ──► profile (features) ──┬─► rule detectors ──────────► severities ─┐
                                 ├─► BehaviorAnomalyModel ────► novelty ────┤
                                 └─► FailureClassifier ◄─(stacked inputs)   │
                                            │ class probabilities           │
                                            └───────────► fusion (logistic) ◄┘
                                                              │
                                                       risk, type, severity

Fusion is a logistic regression fit on a held-out validation split, so the
weight given to each signal is learned rather than hand-tuned. The rule
detectors and the novelty score are also fed to the classifier as inputs
(stacking), so it can learn when a rule fires on benign patterns.

Exact floor: an unregistered tool call (when the agent's tool registry is
known) sets a minimum risk regardless of the learned weights.

Open-set gate: a supervised model only knows the failure types it was
trained on, and confidently calls anything else "healthy". When the two
label-free signals agree -- a rule fires strongly AND the run is unusual
for normal traffic -- the run is flagged even if the classifier disagrees.
Gate thresholds are chosen on validation data under a false-positive
budget. See the leave-one-failure-type-out evaluation in training.py.
"""
from __future__ import annotations

import pickle
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set

import numpy as np
from sklearn.linear_model import LogisticRegression

from . import CLASSES, FAILURE_TYPES
from .bandit import CRITICAL_THRESHOLD, WARN_THRESHOLD
from .detectors import max_severity_by_type, run_detectors
from .features import FEATURE_NAMES, Baseline, RunProfile, feature_vector, profile_run
from .models import BehaviorAnomalyModel, FailureClassifier
from .schema import Run

STACKED_NAMES = FEATURE_NAMES + [f"rule_{t}" for t in FAILURE_TYPES] + ["novelty_score"]
FUSION_INPUTS = ["p_failure", "rule_severity", "novelty_score"]

UI_FEATURES = [
    "n_steps", "max_identical_streak", "duplicate_call_ratio", "near_duplicate_ratio", "tail_cycle_ratio",
    "switch_rate", "error_ratio", "unknown_tool_count", "output_novelty", "recent_novelty", "stall_steps",
    "token_efficiency", "tokens_vs_baseline", "steps_vs_baseline",
]


def exact_floor(p: RunProfile) -> float:
    """Minimum risk implied by unambiguous evidence (0 when there is none)."""
    if p.run.registered_tools and p.unknown_steps:
        return 0.5 if len(p.unknown_steps) == 1 else 0.75
    return 0.0


def severity_of(risk: float) -> str:
    if risk >= CRITICAL_THRESHOLD:
        return "critical"
    if risk >= WARN_THRESHOLD:
        return "warning"
    return "healthy"


@dataclass
class Engine:
    version: str
    unsupervised: BehaviorAnomalyModel
    classifier: FailureClassifier
    fusion: Optional[LogisticRegression]
    known_tools: Dict[str, Set[str]] = field(default_factory=dict)
    baselines: Dict[str, Baseline] = field(default_factory=dict)
    metrics: Dict = field(default_factory=dict)
    open_set: Optional[Dict[str, float]] = None  # {"novelty": n, "rule": r}

    # ------------------------------------------------------------------
    def profile(self, run: Run) -> RunProfile:
        return profile_run(run, self.known_tools.get(run.agent_id), self.baselines.get(run.agent_id))

    def _score_profiles(self, profiles: Sequence[RunProfile]) -> Dict[str, np.ndarray]:
        X = np.vstack([feature_vector(p) for p in profiles])
        signals = [run_detectors(p) for p in profiles]
        rule_mat = np.array([[max_severity_by_type(s).get(t, 0.0) for t in FAILURE_TYPES] for s in signals])
        uns = self.unsupervised.score(X)
        Xs = np.hstack([X, rule_mat, uns["novelty"][:, None]])
        probs = self.classifier.predict_proba(Xs)
        p_fail = 1.0 - probs[:, 0]
        rule_max = rule_mat.max(axis=1)
        risk = self.fuse(p_fail, rule_max, uns["novelty"])
        if self.open_set is not None:
            gate = (uns["novelty"] >= self.open_set["novelty"]) & (rule_max >= self.open_set["rule"])
        else:
            gate = np.zeros(len(X), dtype=bool)
        risk = np.where(gate, np.maximum(risk, 0.5), risk)
        # Exact rules: calling a tool that is not in the agent's registry is a
        # hallucination by definition, so it sets a floor no learned weight can
        # lower (the fusion would otherwise defer to the classifier, which may
        # never have seen this failure).
        floor = np.array([exact_floor(p) for p in profiles])
        exact = floor > 0
        risk = np.maximum(risk, floor)
        gate = gate | exact
        return {
            "X": X, "signals": signals, "rule_mat": rule_mat, "rule_max": rule_max,
            "probs": probs, "p_fail": p_fail, "risk": risk, "gate": gate, **uns,
        }

    def fuse(self, p_fail: np.ndarray, rule_max: np.ndarray, novelty: np.ndarray) -> np.ndarray:
        if self.fusion is None:
            return 1 - (1 - 0.85 * p_fail) * (1 - 0.75 * rule_max) * (1 - 0.4 * novelty)
        Z = np.column_stack([p_fail, rule_max, novelty])
        return self.fusion.predict_proba(Z)[:, 1]

    @staticmethod
    def _failure_type(probs: np.ndarray, rule_row: np.ndarray, risk: float, novelty: float,
                      gated: bool = False) -> Optional[str]:
        if risk < WARN_THRESHOLD:
            return None
        fail_probs = probs[1:]
        mass = fail_probs.sum()
        if mass < 0.2 and gated:
            return FAILURE_TYPES[int(rule_row.argmax())]
        if mass < 0.2 and rule_row.max() < 0.3:
            return "novel_anomaly" if novelty > 0.5 else None
        combined = 0.7 * (fail_probs / max(mass, 1e-9)) + 0.3 * rule_row
        return FAILURE_TYPES[int(combined.argmax())]

    # ------------------------------------------------------------------
    def assess_many(self, runs: Sequence[Run]) -> List[Dict]:
        if not runs:
            return []
        profiles = [self.profile(r) for r in runs]
        s = self._score_profiles(profiles)
        out = []
        for i, (run, prof) in enumerate(zip(runs, profiles)):
            risk = float(s["risk"][i])
            novelty = float(s["novelty"][i])
            gated = bool(s["gate"][i])
            ftype = self._failure_type(s["probs"][i], s["rule_mat"][i], risk, novelty, gated)
            out.append({
                "risk_score": round(risk, 4),
                "severity": severity_of(risk),
                "failure_type": ftype,
                "probabilities": {c: round(float(p), 4) for c, p in zip(CLASSES, s["probs"][i])},
                "rule_severity": round(float(s["rule_max"][i]), 4),
                "supervised_failure_prob": round(float(s["p_fail"][i]), 4),
                "open_set_flag": gated and float(s["p_fail"][i]) < 0.5,
                "novelty_score": round(novelty, 4),
                "isolation_pct": round(float(s["isolation_pct"][i]), 4),
                "knn_pct": round(float(s["knn_pct"][i]), 4),
                "cluster_id": int(s["cluster"][i]),
                "coords": [round(float(v), 4) for v in s["coords"][i]],
                "signals": [sig.to_dict() for sig in s["signals"][i]],
                "features": {k: round(prof.features[k], 4) for k in UI_FEATURES},
                "n_steps": len(run.steps),
                "tokens_vs_baseline": round(prof.features["tokens_vs_baseline"], 4),
                "model_version": self.version,
            })
        return out

    def assess(self, run: Run) -> Dict:
        return self.assess_many([run])[0]

    def trajectory(self, run: Run) -> Dict:
        """Risk after every step -- shows when the failure became detectable."""
        n = len(run.steps)
        if n == 0:
            return {"risk": [], "first_flag_step": None}
        profiles = [self.profile(run.prefix(k)) for k in range(1, n + 1)]
        risk = self._score_profiles(profiles)["risk"]
        flagged = np.where(risk >= WARN_THRESHOLD)[0]
        return {
            "risk": [round(float(r), 4) for r in risk],
            "first_flag_step": int(flagged[0]) if len(flagged) else None,
        }

    def trajectories(self, runs: Sequence[Run]) -> List[Dict]:
        """Batched trajectories: one model call for all prefixes of all runs."""
        profiles, owners = [], []
        for ri, run in enumerate(runs):
            for k in range(1, len(run.steps) + 1):
                profiles.append(self.profile(run.prefix(k)))
                owners.append(ri)
        if not profiles:
            return [{"risk": [], "first_flag_step": None} for _ in runs]
        risk = self._score_profiles(profiles)["risk"]
        owners_arr = np.array(owners)
        out = []
        for ri in range(len(runs)):
            r = risk[owners_arr == ri]
            flagged = np.where(r >= WARN_THRESHOLD)[0]
            out.append({
                "risk": [round(float(v), 4) for v in r],
                "first_flag_step": int(flagged[0]) if len(flagged) else None,
            })
        return out

    # ------------------------------------------------------------------
    def save(self, path: str) -> None:
        with open(path, "wb") as f:
            pickle.dump(self, f)

    @staticmethod
    def load(path: str) -> "Engine":
        with open(path, "rb") as f:
            return pickle.load(f)
