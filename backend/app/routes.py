"""Agent-monitoring HTTP API.

/api/ingest/*   write side, used by instrumented agents (SDK, API key)
/api/*          read side + feedback, used by the dashboard (session) or API keys

Every route is scoped to the caller's workspace.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ml import CLASSES, FAILURE_TYPES
from ml.bandit import ACTION_LABELS, ACTIONS, CRITICAL_THRESHOLD, WARN_THRESHOLD
from ml.features import FEATURE_DESCRIPTIONS

from .auth import Ctx, require_access, role
from .config import get_settings
from .db import get_db
from .orm import Agent, ModelVersion, RunRecord
from .schemas import AgentIn, AssessmentOut, FeedbackIn, RunIn, RunStartIn, StepIn
from .services import analytics, ingest, training
from .services.registry import registry

router = APIRouter(prefix="/api")
member = role("member")


def _assessment(rec: RunRecord) -> AssessmentOut:
    d = rec.decision or {}
    return AssessmentOut(
        run_id=rec.id, step_count=rec.n_steps, risk_score=rec.risk_score, severity=rec.severity,
        failure_type=rec.failure_type, probabilities=rec.probabilities or {}, signals=rec.signals or [],
        recommended_action=rec.recommended_action, action_label=ACTION_LABELS.get(rec.recommended_action, ""),
        action_reason=d.get("reason", ""), first_flag_step=rec.first_flag_step, model_version=rec.model_version,
    )


# ---------------------------------------------------------------- ingest
@router.post("/ingest/runs", response_model=AssessmentOut, tags=["ingest"])
def ingest_run(payload: RunIn, ctx: Ctx = Depends(member), db: Session = Depends(get_db)):
    """Ingest a completed run and score it."""
    return _assessment(ingest.ingest_runs(db, ctx.workspace_id, [payload])[0])


@router.post("/ingest/runs/batch", response_model=List[AssessmentOut], tags=["ingest"])
def ingest_batch(payloads: List[RunIn], ctx: Ctx = Depends(member), db: Session = Depends(get_db)):
    if len(payloads) > 500:
        raise HTTPException(413, "At most 500 runs per batch")
    return [_assessment(r) for r in ingest.ingest_runs(db, ctx.workspace_id, payloads)]


@router.post("/ingest/runs/start", response_model=AssessmentOut, tags=["ingest"])
def start_run(payload: RunStartIn, ctx: Ctx = Depends(member), db: Session = Depends(get_db)):
    """Open a live run. Then POST each step to /ingest/runs/{run_id}/steps."""
    return _assessment(ingest.start_run(db, ctx.workspace_id, payload))


@router.post("/ingest/runs/{run_id}/steps", response_model=AssessmentOut, tags=["ingest"])
def append_step(run_id: str, step: StepIn, ctx: Ctx = Depends(member), db: Session = Depends(get_db)):
    """Append one step; returns the live risk assessment and recommended intervention."""
    return _assessment(ingest.append_step(db, ctx.workspace_id, run_id, step))


@router.post("/ingest/runs/{run_id}/finish", response_model=AssessmentOut, tags=["ingest"])
def finish_run(run_id: str, ctx: Ctx = Depends(member), db: Session = Depends(get_db)):
    return _assessment(ingest.finish_run(db, ctx.workspace_id, run_id))


# ---------------------------------------------------------------- dashboard
@router.get("/meta", tags=["dashboard"])
def meta(ctx: Ctx = Depends(require_access), db: Session = Depends(get_db)):
    active = training.active_version(db)
    return {
        "classes": CLASSES,
        "failure_types": FAILURE_TYPES,
        "actions": [{"id": a, "label": ACTION_LABELS[a]} for a in ACTIONS],
        "thresholds": {"warning": WARN_THRESHOLD, "critical": CRITICAL_THRESHOLD},
        "feature_descriptions": FEATURE_DESCRIPTIONS,
        "agents": [{"id": a.id, "name": a.name}
                   for a in db.query(Agent).filter(Agent.workspace_id == ctx.workspace_id).order_by(Agent.name)],
        "model_version": active.version if active else None,
        "models_loaded": registry.ready,
        "retraining": registry.retraining,
        "role": ctx.role,
    }


@router.get("/overview", tags=["dashboard"])
def overview(hours: int = Query(24, ge=1, le=24 * 90), ctx: Ctx = Depends(require_access), db: Session = Depends(get_db)):
    return analytics.overview(db, ctx.workspace_id, hours)


@router.get("/runs", tags=["dashboard"])
def list_runs(
    agent_id: Optional[str] = None, severity: Optional[str] = None, failure_type: Optional[str] = None,
    status: Optional[str] = None, q: Optional[str] = None, hours: Optional[int] = Query(None, ge=1),
    sort: str = "recent", limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
    ctx: Ctx = Depends(require_access), db: Session = Depends(get_db),
):
    return analytics.list_runs(db, ctx.workspace_id, agent_id=agent_id, severity=severity, failure_type=failure_type,
                               status=status, q=q, hours=hours, sort=sort, limit=limit, offset=offset)


@router.get("/runs/{run_id}", tags=["dashboard"])
def get_run(run_id: str, ctx: Ctx = Depends(require_access), db: Session = Depends(get_db)):
    d = analytics.run_detail(db, ctx.workspace_id, run_id)
    if d is None:
        raise HTTPException(404, "Run not found")
    return d


@router.post("/runs/{run_id}/feedback", tags=["feedback"])
def post_feedback(run_id: str, fb: FeedbackIn, ctx: Ctx = Depends(member), db: Session = Depends(get_db)):
    """Report the true condition and outcome of a run. Updates the policy immediately;
    labels are used by the next classifier retrain."""
    if ctx.user is not None and not fb.reviewer:
        fb.reviewer = ctx.user.email
    row, reward = ingest.record_feedback(db, ctx.workspace_id, run_id, fb)
    retrain_started = training.maybe_auto_retrain(db, get_settings().auto_retrain_every)
    return {"feedback_id": row.id, "reward": row.reward, "policy_updated": reward is not None,
            "retrain_started": retrain_started}


@router.get("/review-queue", tags=["feedback"])
def review_queue(sort: str = Query("uncertainty", pattern="^(uncertainty|risk|recent)$"),
                 agent_id: Optional[str] = None, limit: int = Query(50, ge=1, le=200),
                 ctx: Ctx = Depends(require_access), db: Session = Depends(get_db)):
    return analytics.review_queue(db, ctx.workspace_id, sort=sort, limit=limit, agent_id=agent_id)


@router.get("/agents", tags=["agents"])
def list_agents(hours: int = Query(24 * 7, ge=1), ctx: Ctx = Depends(require_access), db: Session = Depends(get_db)):
    return analytics.agents_summary(db, ctx.workspace_id, hours)


@router.post("/agents", tags=["agents"])
def register_agent(a: AgentIn, ctx: Ctx = Depends(member), db: Session = Depends(get_db)):
    """Register an agent and the tools it is allowed to call (enables exact hallucination detection)."""
    agent = db.get(Agent, (ctx.workspace_id, a.id)) or Agent(workspace_id=ctx.workspace_id, id=a.id)
    agent.name = a.name or a.id
    agent.description = a.description
    agent.model = a.model
    agent.framework = a.framework
    agent.registered_tools = a.registered_tools
    db.add(agent)
    db.commit()
    return analytics.agent_info(agent)


@router.get("/agents/compare", tags=["agents"])
def compare_agents(ids: str, hours: int = Query(24 * 7, ge=1), ctx: Ctx = Depends(require_access),
                   db: Session = Depends(get_db)):
    return analytics.compare_agents(db, ctx.workspace_id, ids.split(","), hours)


@router.get("/agents/{agent_id}", tags=["agents"])
def get_agent(agent_id: str, hours: int = Query(24 * 7, ge=1), ctx: Ctx = Depends(require_access),
              db: Session = Depends(get_db)):
    d = analytics.agent_detail(db, ctx.workspace_id, agent_id, hours)
    if d is None:
        raise HTTPException(404, "Agent not found")
    return d


# Detection models and the intervention policy are shared across workspaces.
@router.get("/models", tags=["models"])
def list_models(ctx: Ctx = Depends(require_access), db: Session = Depends(get_db)):
    rows = db.query(ModelVersion).order_by(ModelVersion.id.desc()).all()
    return {
        "retraining": registry.retraining,
        "versions": [
            {"version": m.version, "created_at": m.created_at.isoformat() + "Z", "trigger": m.trigger,
             "n_train_runs": m.n_train_runs, "n_human_labels": m.n_human_labels, "macro_f1": m.macro_f1,
             "pr_auc": m.pr_auc, "active": m.active, "notes": m.notes}
            for m in rows
        ],
    }


@router.get("/models/{version}/metrics", tags=["models"])
def model_metrics(version: str, ctx: Ctx = Depends(require_access)):
    m = registry.metrics(version)
    if m is None:
        raise HTTPException(404, "Unknown model version")
    return m


@router.post("/models/retrain", tags=["models"])
def retrain(ctx: Ctx = Depends(role("admin"))):
    started = training.retrain_in_background("manual")
    return {"started": started, "message": "Retraining started" if started else "A retrain is already running"}


@router.get("/behavior-map", tags=["models"])
def behavior_map(limit: int = Query(800, ge=50, le=5000), ctx: Ctx = Depends(require_access),
                 db: Session = Depends(get_db)):
    return analytics.behavior_map(db, ctx.workspace_id, limit)


@router.get("/policy", tags=["policy"])
def policy(ctx: Ctx = Depends(require_access), db: Session = Depends(get_db)):
    return analytics.policy_analytics(db, ctx.workspace_id)
