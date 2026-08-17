"""LinUCB contextual bandit for deciding what to do about a flagged agent run.

Actions: continue, retry_step, interrupt_human, escalate_model

The context is a compact summary of the trace embedding plus its anomaly
score (not the raw high-dimensional embedding -- keeps the per-action ridge
regression matrices small and fast to invert online). Reward is supplied
after the fact, once the real outcome of the recommended action is known
(see compute_reward and the /feedback endpoint in api/main.py).
"""
from __future__ import annotations

from typing import Dict

import numpy as np

ACTIONS = ["continue", "retry_step", "interrupt_human", "escalate_model"]

_ACTION_PENALTY: Dict[str, float] = {
    "continue": 0.0,
    "retry_step": -0.1,
    "interrupt_human": -0.3,
    "escalate_model": -0.5,
}


class LinUCBBandit:
    """A standard disjoint LinUCB contextual bandit, one ridge model per action."""

    def __init__(self, n_features: int, alpha: float = 1.0):
        self.n_features = n_features
        self.alpha = alpha
        self.actions = ACTIONS
        self._A = {a: np.eye(n_features) for a in self.actions}
        self._b = {a: np.zeros(n_features) for a in self.actions}

    def select_action(self, context: np.ndarray) -> str:
        context = context.reshape(-1)
        best_action, best_ucb = self.actions[0], -np.inf
        for a in self.actions:
            A_inv = np.linalg.inv(self._A[a])
            theta = A_inv @ self._b[a]
            mean = float(theta @ context)
            confidence = self.alpha * float(np.sqrt(context @ A_inv @ context))
            ucb = mean + confidence
            if ucb > best_ucb:
                best_ucb, best_action = ucb, a
        return best_action

    def update(self, context: np.ndarray, action: str, reward: float) -> None:
        context = context.reshape(-1)
        self._A[action] += np.outer(context, context)
        self._b[action] += reward * context

    @staticmethod
    def build_context(embedding: np.ndarray, anomaly_score: float) -> np.ndarray:
        """Reduce a high-dim trace embedding to a compact, fixed-size context vector."""
        return np.array(
            [
                float(np.mean(embedding)),
                float(np.std(embedding)),
                float(np.max(embedding)),
                anomaly_score,
                1.0,  # bias term
            ],
            dtype=np.float32,
        )


def compute_reward(outcome: str, action: str, steps_saved: int = 0, cost_saved: float = 0.0) -> float:
    """Reward = task-success signal + savings - cost of the intervention itself.

    outcome: "success" | "failure", the eventual real-world outcome of the run
    action: the action the bandit took
    steps_saved / cost_saved: how much wasted work the intervention avoided,
        if measurable (e.g. an interrupt that stopped a run before it burned
        another 10 steps and $2 of API cost)
    """
    base = 1.0 if outcome == "success" else -1.0
    return base + 0.01 * cost_saved + 0.05 * steps_saved + _ACTION_PENALTY.get(action, 0.0)
