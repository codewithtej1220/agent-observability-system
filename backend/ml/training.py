"""Training, evaluation and policy warm-start.

The pipeline is deliberately honest about what each paradigm contributes:
evaluation compares rules-only, unsupervised-only, supervised-only and the
fused engine on the same held-out runs, and early detection is measured as
the number of steps between failure onset and the first alert.
"""
from __future__ import annotations

import random
import time
from collections import Counter, defaultdict
from typing import Dict, List, Optional, Sequence, Set, Tuple

import numpy as np
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score, confusion_matrix, precision_recall_curve,
    precision_recall_fscore_support, roc_auc_score, roc_curve,
)

from . import CLASSES, FAILURE_TYPES
from .bandit import ACTIONS, WARN_THRESHOLD, LinUCBPolicy, STATIC_PLAYBOOK, build_context, compute_reward
from .detectors import max_severity_by_type, run_detectors
from .engine import STACKED_NAMES, Engine
from .features import FEATURE_NAMES, Baseline, feature_vector, profile_run
from .models import BehaviorAnomalyModel, FailureClassifier
from .schema import Run
from .simulator import SUCCESS_PROB, expected_reward, simulate_outcome

# A failure is considered "visible" this many steps after it starts.
VISIBILITY_LAG = {"loop": 2, "tool_thrashing": 3, "hallucinated_tool": 1, "token_waste": 2}


def prefix_label(run: Run, k: int) -> str:
    label = run.source_label or "healthy"
    if label == "healthy" or run.failure_onset is None:
        return label
    return label if k >= run.failure_onset + VISIBILITY_LAG[label] else "healthy"


def learn_known_tools(runs: Sequence[Run], min_ok: int = 3) -> Dict[str, Set[str]]:
    """Registered tools when provided; otherwise tools that returned OK repeatedly."""
    registered: Dict[str, Set[str]] = defaultdict(set)
    ok_counts: Dict[str, Counter] = defaultdict(Counter)
    for r in runs:
        if r.registered_tools:
            registered[r.agent_id].update(r.registered_tools)
        for s in r.steps:
            if s.type == "tool_call" and s.status == "ok" and s.tool_name:
                ok_counts[r.agent_id][s.tool_name] += 1
    out: Dict[str, Set[str]] = {}
    for agent in set(registered) | set(ok_counts):
        out[agent] = registered.get(agent) or {t for t, c in ok_counts[agent].items() if c >= min_ok}
    return out


def learn_baselines(runs: Sequence[Run]) -> Dict[str, Baseline]:
    by_agent: Dict[str, List[Run]] = defaultdict(list)
    for r in runs:
        by_agent[r.agent_id].append(r)
    return {
        a: Baseline(
            median_tokens=float(np.median([r.total_tokens for r in rs])),
            median_steps=float(np.median([len(r.steps) for r in rs])),
        )
        for a, rs in by_agent.items()
    }


def _prefix_samples(runs: Sequence[Run], per_run: int, rng: random.Random,
                    min_len: int = 1) -> List[Tuple[Run, int]]:
    out = []
    for r in runs:
        n = len(r.steps)
        ks = {n}
        if n > min_len:
            ks.update(rng.sample(range(min_len, n), min(per_run - 1, n - min_len)))
        out.extend((r, k) for k in sorted(ks))
    return out


class _Featurizer:
    def __init__(self, known_tools, baselines):
        self.known_tools = known_tools
        self.baselines = baselines

    def profiles(self, runs: Sequence[Run]):
        return [profile_run(r, self.known_tools.get(r.agent_id), self.baselines.get(r.agent_id)) for r in runs]

    def base_and_rules(self, runs: Sequence[Run]):
        profs = self.profiles(runs)
        X = np.vstack([feature_vector(p) for p in profs])
        rules = np.array([[max_severity_by_type(run_detectors(p)).get(t, 0.0) for t in FAILURE_TYPES] for p in profs])
        return X, rules


def train_engine(
    train_runs: Sequence[Run],
    val_runs: Sequence[Run],
    human_runs: Sequence[Tuple[Run, str]] = (),
    version: str = "v1",
    seed: int = 42,
) -> Engine:
    """Fit all models. `human_runs` are (run, human_label) pairs from the review queue."""
    rng = random.Random(seed)
    all_runs = list(train_runs) + [r for r, _ in human_runs]
    known_tools = learn_known_tools(all_runs)
    baselines = learn_baselines(all_runs)
    fz = _Featurizer(known_tools, baselines)

    # 1. Unsupervised: label-free. Fit on prefixes of runs the rules consider clean.
    uns_samples = _prefix_samples(train_runs, per_run=4, rng=rng)
    uns_runs = [r.prefix(k) for r, k in uns_samples]
    X_uns, R_uns = fz.base_and_rules(uns_runs)
    clean = R_uns.max(axis=1) < 0.3
    unsupervised = BehaviorAnomalyModel(random_state=seed).fit(X_uns[clean], FEATURE_NAMES)

    # 2. Supervised: prefix-augmented simulator labels + human labels (upweighted).
    sup_samples = _prefix_samples(train_runs, per_run=6, rng=rng)
    sup_runs = [r.prefix(k) for r, k in sup_samples]
    y = [prefix_label(r, k) for r, k in sup_samples]
    weights = [1.0] * len(sup_runs)
    for run, label in human_runs:
        sup_runs.append(run)
        y.append(label)
        weights.append(3.0)
    X, R = fz.base_and_rules(sup_runs)
    nov = unsupervised.score(X)["novelty"]
    Xs = np.hstack([X, R, nov[:, None]])
    classifier = FailureClassifier(random_state=seed).fit(Xs, y, np.array(weights))

    engine = Engine(version=version, unsupervised=unsupervised, classifier=classifier, fusion=None,
                    known_tools=known_tools, baselines=baselines)

    # 3. Fusion: learn how much to trust each signal on held-out validation prefixes.
    val_samples = _prefix_samples(val_runs, per_run=6, rng=rng)
    val_prefix_runs = [r.prefix(k) for r, k in val_samples]
    y_val = np.array([prefix_label(r, k) != "healthy" for r, k in val_samples], dtype=int)
    s = engine._score_profiles(engine_profiles(engine, val_prefix_runs))
    Z = np.column_stack([s["p_fail"], s["rule_max"], s["novelty"]])
    if len(set(y_val)) == 2:
        engine.fusion = LogisticRegression(C=1.0).fit(Z, y_val)
    engine.open_set = choose_open_set_gate(engine, s, y_val)
    engine.metrics["training"] = {
        "train_runs": len(train_runs),
        "val_runs": len(val_runs),
        "human_labels": len(human_runs),
        "unsupervised_samples": int(clean.sum()),
        "supervised_samples": len(sup_runs),
        "label_distribution": dict(Counter(y)),
        "fusion_weights": (
            {n: round(float(w), 3) for n, w in zip(["p_failure", "rule_severity", "novelty_score"], engine.fusion.coef_[0])}
            | {"intercept": round(float(engine.fusion.intercept_[0]), 3)}
        ) if engine.fusion is not None else None,
        "n_clusters": len(unsupervised.clusters),
        "open_set_gate": engine.open_set,
    }
    return engine


def choose_open_set_gate(engine: Engine, s: Dict, y_val: np.ndarray, max_fpr: float = 0.015) -> Optional[Dict]:
    """Pick the (novelty, rule) gate with the best recall within a false-positive budget."""
    risk = engine.fuse(s["p_fail"], s["rule_max"], s["novelty"])
    healthy, failing = y_val == 0, y_val == 1
    best, best_recall = None, -1.0
    for n in (0.0, 0.5, 0.7, 0.85, 0.95):
        for r in (0.3, 0.5, 0.7, 0.85):
            flag = (risk >= WARN_THRESHOLD) | ((s["novelty"] >= n) & (s["rule_max"] >= r))
            fpr = flag[healthy].mean() if healthy.any() else 0.0
            recall = flag[failing].mean() if failing.any() else 0.0
            if fpr <= max_fpr and recall > best_recall + 1e-9:
                best, best_recall = {"novelty": n, "rule": r}, recall
    return best


def engine_profiles(engine: Engine, runs: Sequence[Run]):
    return [engine.profile(r) for r in runs]


# --------------------------------------------------------------------------
# Evaluation
# --------------------------------------------------------------------------

def _downsample(xs, ys, n=60):
    if len(xs) <= n:
        return [[round(float(a), 4), round(float(b), 4)] for a, b in zip(xs, ys)]
    idx = np.linspace(0, len(xs) - 1, n).astype(int)
    return [[round(float(xs[i]), 4), round(float(ys[i]), 4)] for i in idx]


def _recall_at_fpr(y, score, target_fpr=0.05):
    fpr, tpr, _ = roc_curve(y, score)
    ok = fpr <= target_fpr
    return float(tpr[ok].max()) if ok.any() else 0.0


def evaluate(engine: Engine, test_runs: Sequence[Run], seed: int = 0) -> Dict:
    t0 = time.time()
    profiles = engine_profiles(engine, test_runs)
    s = engine._score_profiles(profiles)
    y_true = [r.source_label or "healthy" for r in test_runs]
    y_bin = np.array([y != "healthy" for y in y_true], dtype=int)

    # Multi-class prediction
    y_pred = []
    for i in range(len(test_runs)):
        ft = Engine._failure_type(s["probs"][i], s["rule_mat"][i], float(s["risk"][i]), float(s["novelty"][i]),
                                  bool(s["gate"][i]))
        if ft == "novel_anomaly":
            ft = FAILURE_TYPES[int(s["probs"][i][1:].argmax())]
        y_pred.append(ft or "healthy")
    p, r, f, sup = precision_recall_fscore_support(y_true, y_pred, labels=CLASSES, zero_division=0)
    per_class = [
        {"class": c, "precision": round(float(p[i]), 4), "recall": round(float(r[i]), 4),
         "f1": round(float(f[i]), 4), "support": int(sup[i])}
        for i, c in enumerate(CLASSES)
    ]
    cm = confusion_matrix(y_true, y_pred, labels=CLASSES).tolist()

    # Binary: compare paradigms on the same runs.
    approaches = {
        "Rules only": s["rule_max"],
        "Unsupervised only": 0.6 * s["isolation_pct"] + 0.4 * s["knn_pct"],
        "Supervised only": s["p_fail"],
        "Fused engine": s["risk"],
    }
    comparison = []
    pr_curves = {}
    for name, score in approaches.items():
        prec, rec, _ = precision_recall_curve(y_bin, score)
        pr_curves[name] = _downsample(rec[::-1], prec[::-1])
        comparison.append({
            "approach": name,
            "roc_auc": round(float(roc_auc_score(y_bin, score)), 4),
            "pr_auc": round(float(average_precision_score(y_bin, score)), 4),
            "recall_at_5pct_fpr": round(_recall_at_fpr(y_bin, score), 4),
        })
    risk = s["risk"]
    flagged = risk >= WARN_THRESHOLD
    tp = int((flagged & (y_bin == 1)).sum())
    fp = int((flagged & (y_bin == 0)).sum())
    fn = int((~flagged & (y_bin == 1)).sum())
    tn = int((~flagged & (y_bin == 0)).sum())
    prec = tp / max(1, tp + fp)
    rec = tp / max(1, tp + fn)
    fpr_curve, tpr_curve, _ = roc_curve(y_bin, risk)
    binary = {
        "threshold": WARN_THRESHOLD,
        "precision": round(prec, 4),
        "recall": round(rec, 4),
        "f1": round(2 * prec * rec / max(1e-9, prec + rec), 4),
        "false_positive_rate": round(fp / max(1, fp + tn), 4),
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "roc_curve": _downsample(fpr_curve, tpr_curve),
    }

    # Early detection: risk after every step of each failing run.
    failing = [r for r in test_runs if (r.source_label or "healthy") != "healthy"]
    healthy = [r for r in test_runs if (r.source_label or "healthy") == "healthy"]
    traj_fail = engine.trajectories(failing)
    traj_ok = engine.trajectories(healthy)
    latencies: List[Optional[int]] = []
    saved_tokens, total_tokens = 0, 0
    by_type: Dict[str, List[Optional[int]]] = defaultdict(list)
    for run, tr in zip(failing, traj_fail):
        ff = tr["first_flag_step"]
        lat = None if ff is None else max(0, ff - (run.failure_onset or 0))
        latencies.append(lat)
        by_type[run.source_label].append(lat)
        total_tokens += run.total_tokens
        if ff is not None:
            saved_tokens += sum(st.tokens for st in run.steps[ff + 1:])
    hist = Counter("never" if l is None else (str(l) if l < 5 else "5+") for l in latencies)
    early = {
        "detected_rate": round(sum(l is not None for l in latencies) / max(1, len(latencies)), 4),
        "median_latency_steps": float(np.median([l for l in latencies if l is not None])) if any(l is not None for l in latencies) else None,
        "within_2_steps": round(sum(l is not None and l <= 2 for l in latencies) / max(1, len(latencies)), 4),
        "latency_histogram": [{"bucket": b, "count": hist.get(b, 0)} for b in ["0", "1", "2", "3", "4", "5+", "never"]],
        "avoidable_token_share": round(saved_tokens / max(1, total_tokens), 4),
        "healthy_ever_flagged_rate": round(sum(t["first_flag_step"] is not None for t in traj_ok) / max(1, len(traj_ok)), 4),
        "by_type": [
            {"failure_type": ft,
             "detected_rate": round(sum(l is not None for l in ls) / len(ls), 4),
             "median_latency_steps": float(np.median([l for l in ls if l is not None])) if any(l is not None for l in ls) else None}
            for ft, ls in sorted(by_type.items())
        ],
    }

    # Per-agent detection quality.
    by_agent = []
    agents = sorted({r.agent_id for r in test_runs})
    for a in agents:
        idx = [i for i, run in enumerate(test_runs) if run.agent_id == a]
        yb, fl = y_bin[idx], flagged[idx]
        by_agent.append({
            "agent_id": a,
            "runs": len(idx),
            "recall": round(float((fl & (yb == 1)).sum() / max(1, (yb == 1).sum())), 4),
            "false_positive_rate": round(float((fl & (yb == 0)).sum() / max(1, (yb == 0).sum())), 4),
        })

    # Which inputs the supervised model relies on.
    Xs = np.hstack([s["X"], s["rule_mat"], s["novelty"][:, None]])
    y_idx = np.array([CLASSES.index(y) for y in y_true])
    take = np.random.default_rng(seed).choice(len(Xs), size=min(1500, len(Xs)), replace=False)
    pi = permutation_importance(engine.classifier.model, Xs[take], y_idx[take], n_repeats=4,
                                random_state=seed, scoring="f1_macro")
    importance = sorted(
        ({"feature": n, "importance": round(float(v), 4)} for n, v in zip(STACKED_NAMES, pi.importances_mean)),
        key=lambda d: d["importance"], reverse=True,
    )[:15]

    return {
        "test_runs": len(test_runs),
        "class_distribution": dict(Counter(y_true)),
        "binary": binary,
        "per_class": per_class,
        "macro_f1": round(float(np.mean([c["f1"] for c in per_class])), 4),
        "confusion_matrix": {"labels": CLASSES, "matrix": cm},
        "approach_comparison": comparison,
        "pr_curves": pr_curves,
        "early_detection": early,
        "by_agent": by_agent,
        "feature_importance": importance,
        "eval_seconds": round(time.time() - t0, 2),
    }


def unseen_failure_robustness(train_runs: Sequence[Run], val_runs: Sequence[Run], test_runs: Sequence[Run],
                              seed: int = 42) -> List[Dict]:
    """Leave-one-failure-type-out: how each approach handles a failure it never saw in training.

    This is the case that matters in production -- new agent versions fail
    in new ways -- and it is where the label-free signals earn their keep.
    """
    out = []
    for held in FAILURE_TYPES:
        eng = train_engine([r for r in train_runs if r.source_label != held],
                           [r for r in val_runs if r.source_label != held], seed=seed)
        runs = [r for r in test_runs if r.source_label in (held, "healthy")]
        s = eng._score_profiles(engine_profiles(eng, runs))
        y = np.array([r.source_label == held for r in runs])
        for name, flag in [
            ("Rules only", s["rule_max"] >= WARN_THRESHOLD),
            ("Unsupervised only", s["novelty"] >= 0.5),
            ("Supervised only", s["p_fail"] >= 0.5),
            ("Fused engine", s["risk"] >= WARN_THRESHOLD),
        ]:
            out.append({
                "held_out": held,
                "approach": name,
                "recall": round(float((flag & y).sum() / max(1, y.sum())), 4),
                "false_positive_rate": round(float((flag & ~y).sum() / max(1, (~y).sum())), 4),
            })
    return out


# --------------------------------------------------------------------------
# Policy warm start (offline simulation)
# --------------------------------------------------------------------------

def warm_start_policy(engine: Engine, runs: Sequence[Run], rounds: int = 4000, seed: int = 1) -> Tuple[LinUCBPolicy, Dict]:
    """Pre-train the bandit against the simulator's outcome model.

    The policy only sees what the engine sees (the assessment), never the
    true label. Compared against: a hand-written playbook keyed on the
    predicted failure type, always paging a human, a random policy, and an
    oracle that knows the true label (upper bound).
    """
    rng = np.random.default_rng(seed)
    py_rng = random.Random(seed)
    # Contexts: assessments at the first flagged prefix (when the policy would actually act).
    pool = []
    trajectories = engine.trajectories(runs)
    for run, tr in zip(runs, trajectories):
        ff = tr["first_flag_step"]
        if ff is None:
            continue
        a = engine.assess(run.prefix(ff + 1))
        pool.append((a, run.source_label or "healthy"))
    if not pool:
        return LinUCBPolicy(), {}

    policy = LinUCBPolicy()
    totals = {"LinUCB policy": 0.0, "Static playbook": 0.0, "Always human review": 0.0, "Random": 0.0, "Oracle": 0.0}
    curve = []
    action_by_label: Dict[str, Counter] = defaultdict(Counter)
    for t in range(1, rounds + 1):
        assessment, label = pool[py_rng.randrange(len(pool))]
        dec = policy.decide(assessment)
        action = dec.action
        resolved = simulate_outcome(rng, label, action)
        reward = compute_reward(resolved, action, label)
        if dec.by_policy:
            policy.update(build_context(assessment), action, reward)
        if t > rounds * 0.75:
            action_by_label[label][action] += 1
        totals["LinUCB policy"] += reward
        static = STATIC_PLAYBOOK.get(assessment["failure_type"] or "healthy", "human_review")
        if assessment["risk_score"] >= 0.7 and static == "continue":
            static = "human_review"
        totals["Static playbook"] += expected_reward(label, static)
        totals["Always human review"] += expected_reward(label, "human_review")
        allowed = policy.allowed_actions(assessment["risk_score"])
        totals["Random"] += np.mean([expected_reward(label, a) for a in allowed])
        totals["Oracle"] += max(expected_reward(label, a) for a in allowed)
        if t % 100 == 0:
            curve.append({"round": t, **{k: round(v / t, 4) for k, v in totals.items()}})

    labels = sorted(action_by_label)
    report = {
        "rounds": rounds,
        "context_pool": len(pool),
        "learning_curve": curve,
        "final_avg_reward": {k: round(v / rounds, 4) for k, v in totals.items()},
        "action_by_true_label": {
            "labels": labels,
            "actions": ACTIONS,
            "matrix": [[action_by_label[l][a] for a in ACTIONS] for l in labels],
        },
        "success_model": SUCCESS_PROB,
    }
    return policy, report
