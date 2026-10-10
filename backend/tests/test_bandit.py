import numpy as np

from ml.bandit import ACTIONS, CRITICAL_THRESHOLD, LinUCBPolicy, build_context, compute_reward


def _assessment(risk, **probs):
    return {"risk_score": risk, "probabilities": probs, "rule_severity": 0.0, "novelty_score": 0.0,
            "n_steps": 5, "tokens_vs_baseline": 1.0}


def test_sherman_morrison_matches_direct_inverse():
    rng = np.random.default_rng(0)
    p = LinUCBPolicy()
    A = np.eye(p.d)
    for _ in range(30):
        x = rng.random(p.d)
        p.update(x, "reflect", 1.0)
        A += np.outer(x, x)
    assert np.allclose(p.A_inv["reflect"], np.linalg.inv(A), atol=1e-8)


def test_low_risk_always_continues():
    d = LinUCBPolicy().decide(_assessment(0.1))
    assert d.action == "continue" and not d.by_policy


def test_critical_risk_never_continues():
    p = LinUCBPolicy()
    # Even if "continue" has been rewarded heavily, the guardrail removes it.
    for _ in range(50):
        p.update(build_context(_assessment(0.9, loop=0.9)), "continue", 5.0)
    d = p.decide(_assessment(CRITICAL_THRESHOLD + 0.1, loop=0.9))
    assert d.action != "continue" and "continue" not in d.allowed


def test_learns_context_dependent_best_action():
    rng = np.random.default_rng(1)
    p = LinUCBPolicy()
    best = {"loop": "reflect", "token_waste": "terminate"}
    for _ in range(1500):
        ft = rng.choice(list(best))
        a = _assessment(0.8, **{ft: 0.95})
        dec = p.decide(a)
        reward = 1.0 if dec.action == best[ft] else 0.0
        p.update(build_context(a), dec.action, reward + rng.normal(0, 0.1))
    for ft, action in best.items():
        assert p.decide(_assessment(0.8, **{ft: 0.95}), explore=False).action == action


def test_policy_roundtrip():
    p = LinUCBPolicy()
    p.update(np.ones(p.d), "terminate", 0.5)
    q = LinUCBPolicy.from_dict(p.to_dict())
    assert q.n_updates == 1 and q.counts["terminate"] == 1
    assert np.allclose(q.A_inv["terminate"], p.A_inv["terminate"])


def test_reward_shape():
    assert compute_reward(True, "continue", "healthy") > compute_reward(True, "human_review", "healthy")
    assert compute_reward(False, "terminate", "loop") > compute_reward(False, "continue", "loop")
    assert compute_reward(False, "terminate", "healthy") < 0
    assert set(ACTIONS) >= {"continue", "terminate"}
