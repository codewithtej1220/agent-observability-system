"""Intervention policy: a LinUCB contextual bandit with safety guardrails.

Given what the detectors and models believe about a run, choose what to do:

    continue        let the agent proceed
    reflect         inject a self-correction prompt ("you are repeating...")
    retry_step      re-run the last step with the valid tool list / fixed args
    escalate_model  hand the run to a stronger model
    human_review    pause and page a human
    terminate       stop the run to cap wasted spend

Context is the *detection output* (risk, per-failure probabilities, rule
severity, novelty, run length, relative spend) -- a compact, meaningful
representation, so the policy learns e.g. "loops respond to reflection,
thrashing needs a stronger model". Reward comes from real outcomes reported
through the feedback API.

Guardrails keep the bandit from doing anything unsafe while it explores:
low-risk runs always continue, and high-risk runs are never told to continue.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

ACTIONS = ["continue", "reflect", "retry_step", "escalate_model", "human_review", "terminate"]

ACTION_LABELS = {
    "continue": "Continue",
    "reflect": "Inject reflection prompt",
    "retry_step": "Retry step with corrections",
    "escalate_model": "Escalate to stronger model",
    "human_review": "Request human review",
    "terminate": "Terminate run",
}

ACTION_COST = {
    "continue": 0.0,
    "reflect": 0.05,
    "retry_step": 0.05,
    "escalate_model": 0.25,
    "human_review": 0.45,
    "terminate": 0.0,
}

CONTEXT_NAMES = [
    "bias", "risk", "p_loop", "p_tool_thrashing", "p_hallucinated_tool", "p_token_waste",
    "rule_severity", "novelty", "run_length", "relative_spend",
]

WARN_THRESHOLD = 0.35
CRITICAL_THRESHOLD = 0.7


def compute_reward(resolved: bool, action: str, true_label: Optional[str]) -> float:
    """Outcome-based reward.

    +1 if the run ultimately succeeded, minus the cost of the intervention
    (human time, stronger-model spend). Letting a genuinely failing run
    continue to failure burns tokens and is penalized; terminating a failing
    run early is partially rewarded because it caps the waste; terminating a
    healthy run is penalized.
    """
    failing = true_label is not None and true_label != "healthy"
    r = (1.0 if resolved else 0.0) - ACTION_COST[action]
    if action == "terminate":
        r += 0.35 if failing else -0.6
    elif failing and not resolved:
        r -= 0.3
    return float(r)


def build_context(assessment: Dict) -> np.ndarray:
    probs = assessment.get("probabilities", {})
    return np.array([
        1.0,
        assessment.get("risk_score", 0.0),
        probs.get("loop", 0.0),
        probs.get("tool_thrashing", 0.0),
        probs.get("hallucinated_tool", 0.0),
        probs.get("token_waste", 0.0),
        assessment.get("rule_severity", 0.0),
        assessment.get("novelty_score", 0.0),
        min(assessment.get("n_steps", 0) / 30.0, 1.0),
        min(assessment.get("tokens_vs_baseline", 0.0) / 5.0, 1.0),
    ], dtype=np.float64)


@dataclass
class Decision:
    action: str
    reason: str
    scores: Dict[str, Dict[str, float]]  # action -> {mean, bonus, ucb}
    allowed: List[str]
    by_policy: bool

    def to_dict(self) -> Dict:
        return {
            "action": self.action,
            "label": ACTION_LABELS[self.action],
            "reason": self.reason,
            "scores": self.scores,
            "allowed": self.allowed,
            "by_policy": self.by_policy,
        }


class LinUCBPolicy:
    def __init__(self, n_features: int = len(CONTEXT_NAMES), alpha: float = 1.0, ridge: float = 1.0):
        self.d = n_features
        self.alpha = alpha
        self.A_inv = {a: np.eye(n_features) / ridge for a in ACTIONS}
        self.b = {a: np.zeros(n_features) for a in ACTIONS}
        self.counts = {a: 0 for a in ACTIONS}
        self.reward_sums = {a: 0.0 for a in ACTIONS}
        self.n_updates = 0

    # -- decision ---------------------------------------------------------
    def allowed_actions(self, risk: float) -> List[str]:
        if risk >= CRITICAL_THRESHOLD:
            return [a for a in ACTIONS if a != "continue"]
        return list(ACTIONS)

    def score(self, x: np.ndarray, actions: List[str]) -> Dict[str, Dict[str, float]]:
        out = {}
        for a in actions:
            theta = self.A_inv[a] @ self.b[a]
            mean = float(theta @ x)
            bonus = float(self.alpha * np.sqrt(max(0.0, x @ self.A_inv[a] @ x)))
            out[a] = {"mean": round(mean, 4), "bonus": round(bonus, 4), "ucb": round(mean + bonus, 4)}
        return out

    def decide(self, assessment: Dict, explore: bool = True) -> Decision:
        risk = assessment.get("risk_score", 0.0)
        if risk < WARN_THRESHOLD:
            return Decision("continue", "Risk below warning threshold; no intervention needed.", {}, ["continue"], False)
        x = build_context(assessment)
        allowed = self.allowed_actions(risk)
        scores = self.score(x, allowed)
        key = "ucb" if explore else "mean"
        action = max(allowed, key=lambda a: scores[a][key])
        if self.counts[action] == 0:
            reason = "Exploring: no feedback yet for this action in similar contexts."
        else:
            reason = (f"Highest expected reward ({scores[action]['mean']:+.2f}) for this risk profile, "
                      f"learned from {self.n_updates} outcomes.")
        return Decision(action, reason, scores, allowed, True)

    # -- learning ---------------------------------------------------------
    def update(self, x: np.ndarray, action: str, reward: float) -> None:
        A_inv = self.A_inv[action]
        Ax = A_inv @ x
        self.A_inv[action] = A_inv - np.outer(Ax, Ax) / (1.0 + x @ Ax)  # Sherman-Morrison
        self.b[action] = self.b[action] + reward * x
        self.counts[action] += 1
        self.reward_sums[action] += reward
        self.n_updates += 1

    def weights(self) -> Dict[str, Dict[str, float]]:
        return {
            a: {name: round(float(v), 4) for name, v in zip(CONTEXT_NAMES, self.A_inv[a] @ self.b[a])}
            for a in ACTIONS
        }

    def summary(self) -> Dict:
        return {
            "alpha": self.alpha,
            "n_updates": self.n_updates,
            "actions": [
                {
                    "action": a,
                    "label": ACTION_LABELS[a],
                    "count": self.counts[a],
                    "mean_reward": round(self.reward_sums[a] / self.counts[a], 4) if self.counts[a] else None,
                    "cost": ACTION_COST[a],
                }
                for a in ACTIONS
            ],
            "weights": self.weights(),
            "context_features": CONTEXT_NAMES,
        }

    # -- persistence ------------------------------------------------------
    def to_dict(self) -> Dict:
        return {
            "d": self.d,
            "alpha": self.alpha,
            "A_inv": {a: self.A_inv[a].tolist() for a in ACTIONS},
            "b": {a: self.b[a].tolist() for a in ACTIONS},
            "counts": self.counts,
            "reward_sums": self.reward_sums,
            "n_updates": self.n_updates,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "LinUCBPolicy":
        p = cls(n_features=d["d"], alpha=d["alpha"])
        for a in ACTIONS:
            if a in d["A_inv"]:
                p.A_inv[a] = np.array(d["A_inv"][a])
                p.b[a] = np.array(d["b"][a])
                p.counts[a] = d["counts"].get(a, 0)
                p.reward_sums[a] = d["reward_sums"].get(a, 0.0)
        p.n_updates = d.get("n_updates", 0)
        return p


STATIC_PLAYBOOK = {
    "healthy": "continue",
    "loop": "retry_step",
    "tool_thrashing": "human_review",
    "hallucinated_tool": "escalate_model",
    "token_waste": "terminate",
    "novel_anomaly": "human_review",
}
