"""Model (re)training and promotion.

Each training run produces a new model version that is evaluated on a
held-out test set. A new version is promoted only if it is not worse than
the active one (macro-F1 within tolerance), so human labels can never
silently degrade detection.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from ml.schema import Run
from ml.simulator import generate_dataset
from ml.training import evaluate, train_engine, unseen_failure_robustness, warm_start_policy

from ..db import SessionLocal
from ..orm import Agent, Feedback, ModelVersion, RunRecord
from .ingest import to_ml_run
from .registry import registry

log = logging.getLogger(__name__)
PROMOTION_TOLERANCE = 0.02

# Fixed seeds keep the simulated reference data identical across versions,
# so version-to-version metric changes come from the models, not the data.
TRAIN_SEED, VAL_SEED, TEST_SEED, POLICY_SEED = 101, 202, 303, 404


def reference_data() -> Tuple[List[Run], List[Run], List[Run]]:
    train = generate_dataset(2500, seed=TRAIN_SEED, balanced=True)
    val = generate_dataset(800, seed=VAL_SEED)
    test = generate_dataset(1500, seed=TEST_SEED, failure_scale=1.5)
    return train, val, test


def human_labeled_runs(db: Session) -> List[Tuple[Run, str, int]]:
    """Latest human label per run, as (run, label, feedback_id)."""
    out: Dict[str, Tuple[Run, str, int]] = {}
    agents = {(a.workspace_id, a.id): a for a in db.query(Agent).all()}
    rows = db.query(Feedback, RunRecord).join(RunRecord, Feedback.run_id == RunRecord.id).order_by(Feedback.id).all()
    for fb, rec in rows:
        out[rec.id] = (to_ml_run(rec, agents.get((rec.workspace_id, rec.agent_id))), fb.label, fb.id)
    return list(out.values())


def _next_version(db: Session) -> str:
    return f"v{db.query(ModelVersion).count() + 1}"


def train_new_version(db: Session, trigger: str, robustness: bool = False) -> ModelVersion:
    t0 = time.time()
    train, val, test = reference_data()
    human = human_labeled_runs(db)
    version = _next_version(db)
    engine = train_engine(train, val, [(r, l) for r, l, _ in human], version=version)
    metrics = evaluate(engine, test)
    metrics["training"] = engine.metrics["training"]
    metrics["version"] = version
    metrics["trigger"] = trigger

    if human:
        labeled = [r for r, _, _ in human]
        preds = engine.assess_many(labeled)
        agree = sum((p["failure_type"] or "healthy") == l for p, (_, l, _) in zip(preds, human))
        metrics["human_label_agreement"] = {"labels": len(human), "agreement": round(agree / len(human), 4),
                                            "note": "In-sample: these labels were used for training."}

    active = db.query(ModelVersion).filter(ModelVersion.active.is_(True)).first()
    if robustness:
        metrics["unseen_failure_robustness"] = unseen_failure_robustness(train, val, test)
    elif active is not None:
        prev = registry.metrics(active.version) or {}
        if "unseen_failure_robustness" in prev:
            metrics["unseen_failure_robustness"] = prev["unseen_failure_robustness"]
            metrics["unseen_failure_robustness_from"] = prev.get("unseen_failure_robustness_from", active.version)
    metrics["training_seconds"] = round(time.time() - t0, 1)

    fused = next(c for c in metrics["approach_comparison"] if c["approach"] == "Fused engine")
    promote = active is None or metrics["macro_f1"] >= active.macro_f1 - PROMOTION_TOLERANCE
    mv = ModelVersion(
        version=version, trigger=trigger, n_train_runs=len(train), n_human_labels=len(human),
        macro_f1=metrics["macro_f1"], pr_auc=fused["pr_auc"], active=promote,
        notes="Promoted" if promote else f"Not promoted: macro-F1 {metrics['macro_f1']:.3f} < active {active.macro_f1:.3f}",
    )
    registry.save_engine(engine, metrics)
    if promote:
        if active is not None:
            active.active = False
        registry.activate(engine)
    for _, _, fid in human:
        fb = db.get(Feedback, fid)
        if fb is not None and fb.used_in_version is None:
            fb.used_in_version = version
    db.add(mv)
    db.commit()
    log.info("Trained %s in %.1fs (macro-F1 %.3f, promoted=%s)", version, time.time() - t0, metrics["macro_f1"], promote)
    return mv


def warm_start(db: Session) -> Dict:
    assert registry.engine is not None
    runs = generate_dataset(1500, seed=POLICY_SEED)
    policy, report = warm_start_policy(registry.engine, runs)
    registry.set_policy(policy, report)
    return report


def retrain_in_background(trigger: str) -> bool:
    """Start a retrain unless one is already running. Returns True if started."""
    with registry.lock:
        if registry.retraining:
            return False
        registry.retraining = True

    def _job():
        db = SessionLocal()
        try:
            train_new_version(db, trigger)
        except Exception:  # noqa: BLE001
            log.exception("Retraining failed")
        finally:
            db.close()
            registry.retraining = False

    threading.Thread(target=_job, daemon=True, name="retrain").start()
    return True


def maybe_auto_retrain(db: Session, every: int) -> bool:
    if every <= 0:
        return False
    pending = db.query(Feedback).filter(Feedback.used_in_version.is_(None)).count()
    return pending >= every and retrain_in_background("auto: new human labels")


def active_version(db: Session) -> Optional[ModelVersion]:
    return db.query(ModelVersion).filter(ModelVersion.active.is_(True)).first()
