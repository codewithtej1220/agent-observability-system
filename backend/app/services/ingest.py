"""Ingestion: turn incoming runs/steps into assessments, decisions and rows.

Two modes:
  * full run   -- POST a completed run; it is scored post-hoc, including the
                  step at which it *would* have been flagged.
  * streaming  -- start a run, POST each step as it happens, and get back the
                  current risk and recommended intervention after every step.
                  This is how an agent loop uses the system to stop failures
                  while they happen.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Sequence, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ml.bandit import ACTIONS, WARN_THRESHOLD, build_context, compute_reward
from ml.schema import Run, Step

from ..orm import Agent, Feedback, PolicyEvent, RunRecord, StepRecord, utcnow
from ..pricing import estimate_cost
from ..schemas import FeedbackIn, RunIn, RunStartIn, StepIn
from .registry import registry

SEVERITY_RANK = {"healthy": 0, "warning": 1, "critical": 2}


def _require_ready():
    if not registry.ready:
        raise HTTPException(503, "Models are not loaded. Run `python -m scripts.bootstrap` in backend/.")
    return registry.engine, registry.policy


def ensure_agent(db: Session, agent_id: str, registered_tools: Optional[List[str]] = None, model: str = "") -> Agent:
    agent = db.get(Agent, agent_id)
    if agent is None:
        agent = Agent(id=agent_id, name=agent_id, model=model, registered_tools=registered_tools)
        db.add(agent)
        db.flush()
    elif registered_tools and not agent.registered_tools:
        agent.registered_tools = registered_tools
    return agent


def to_ml_run(rec: RunRecord, agent: Optional[Agent]) -> Run:
    return Run(
        run_id=rec.id,
        agent_id=rec.agent_id,
        task=rec.task,
        model=rec.model,
        registered_tools=agent.registered_tools if agent else None,
        steps=[
            Step(index=s.idx, type=s.type, tool_name=s.tool_name, arguments=s.arguments or {}, output=s.output,
                 status=s.status, latency_ms=s.latency_ms, input_tokens=s.input_tokens, output_tokens=s.output_tokens)
            for s in rec.steps
        ],
        source_label=rec.source_label,
        failure_onset=rec.failure_onset,
    )


def _step_record(i: int, s: StepIn, ts: Optional[datetime]) -> StepRecord:
    return StepRecord(idx=i, type=s.type, tool_name=s.tool_name, arguments=s.arguments, output=s.output,
                      status=s.status, latency_ms=s.latency_ms, input_tokens=s.input_tokens,
                      output_tokens=s.output_tokens, timestamp=s.timestamp or ts)


def _refresh_totals(rec: RunRecord) -> None:
    rec.n_steps = len(rec.steps)
    rec.input_tokens = sum(s.input_tokens for s in rec.steps)
    rec.output_tokens = sum(s.output_tokens for s in rec.steps)
    rec.total_latency_ms = round(sum(s.latency_ms for s in rec.steps), 1)
    rec.cost_usd = round(estimate_cost(rec.model, rec.input_tokens, rec.output_tokens), 6)
    rec.has_final_answer = bool(rec.steps) and rec.steps[-1].type == "final_answer"


def _apply_assessment(rec: RunRecord, a: Dict) -> None:
    rec.risk_score = a["risk_score"]
    rec.severity = a["severity"]
    rec.failure_type = a["failure_type"]
    rec.probabilities = a["probabilities"]
    rec.signals = a["signals"]
    rec.features = a["features"]
    rec.rule_severity = a["rule_severity"]
    rec.novelty_score = a["novelty_score"]
    rec.open_set_flag = a["open_set_flag"]
    rec.cluster_id = a["cluster_id"]
    rec.coords = a["coords"]
    rec.model_version = a["model_version"]


def _apply_decision(db: Session, rec: RunRecord, a: Dict, decision, at_step: int) -> None:
    rec.recommended_action = decision.action
    rec.decision = {**decision.to_dict(), "at_step": at_step, "risk_at_decision": a["risk_score"],
                    "failure_type_at_decision": a["failure_type"]}
    rec.policy_context = build_context(a).tolist() if decision.by_policy else []
    if decision.by_policy:
        db.add(PolicyEvent(run_id=rec.id, action=decision.action, failure_type=a["failure_type"],
                           risk_score=a["risk_score"], created_at=rec.started_at + timedelta(seconds=at_step)))


def _finalize_waste(rec: RunRecord) -> None:
    ff = rec.first_flag_step
    if ff is not None and rec.severity != "healthy":
        rec.avoidable_tokens = sum(s.input_tokens + s.output_tokens for s in rec.steps[ff + 1:])
    else:
        rec.avoidable_tokens = 0


# --------------------------------------------------------------------------
# Full-run ingestion (single and batched)
# --------------------------------------------------------------------------

def ingest_runs(db: Session, payloads: Sequence[RunIn]) -> List[RunRecord]:
    """Batched: one model call for all runs, one for all prefixes. Used by the API and the seeder."""
    engine, policy = _require_ready()
    records: List[RunRecord] = []
    ml_runs: List[Run] = []
    for p in payloads:
        if not p.steps:
            raise HTTPException(422, "A run needs at least one step")
        run_id = p.run_id or str(uuid.uuid4())
        if db.get(RunRecord, run_id) is not None:
            raise HTTPException(409, f"Run {run_id} already exists")
        agent = ensure_agent(db, p.agent_id, p.registered_tools, p.model)
        started = p.started_at or utcnow()
        rec = RunRecord(id=run_id, agent_id=agent.id, task=p.task, model=p.model or agent.model,
                        started_at=started, source_label=p.source_label, failure_onset=p.failure_onset)
        t = started
        for i, s in enumerate(p.steps):
            rec.steps.append(_step_record(i, s, t))
            t = t + timedelta(milliseconds=s.latency_ms + 200)
        rec.ended_at = t
        rec.status = "completed" if p.steps[-1].type == "final_answer" else "incomplete"
        _refresh_totals(rec)
        records.append(rec)
        ml_runs.append(to_ml_run(rec, agent))

    final = engine.assess_many(ml_runs)
    trajectories = engine.trajectories(ml_runs)

    # The policy acts at the moment the run first crossed the warning threshold.
    flagged = [(i, tr["first_flag_step"]) for i, tr in enumerate(trajectories) if tr["first_flag_step"] is not None]
    at_flag = engine.assess_many([ml_runs[i].prefix(ff + 1) for i, ff in flagged]) if flagged else []
    decision_ctx = {i: (ff, a) for (i, ff), a in zip(flagged, at_flag)}

    with registry.lock:
        for i, rec in enumerate(records):
            _apply_assessment(rec, final[i])
            rec.risk_trajectory = trajectories[i]["risk"]
            rec.first_flag_step = trajectories[i]["first_flag_step"]
            _finalize_waste(rec)
            db.add(rec)
            if i in decision_ctx:
                ff, a = decision_ctx[i]
                _apply_decision(db, rec, a, policy.decide(a), ff)
            else:
                _apply_decision(db, rec, final[i], policy.decide(final[i]), rec.n_steps - 1)
    db.commit()
    return records


# --------------------------------------------------------------------------
# Streaming ingestion
# --------------------------------------------------------------------------

def start_run(db: Session, p: RunStartIn) -> RunRecord:
    _require_ready()
    run_id = p.run_id or str(uuid.uuid4())
    if db.get(RunRecord, run_id) is not None:
        raise HTTPException(409, f"Run {run_id} already exists")
    agent = ensure_agent(db, p.agent_id, p.registered_tools, p.model)
    rec = RunRecord(id=run_id, agent_id=agent.id, task=p.task, model=p.model or agent.model,
                    started_at=p.started_at or utcnow(), status="running")
    db.add(rec)
    db.commit()
    return rec


def _get_run(db: Session, run_id: str) -> RunRecord:
    rec = db.get(RunRecord, run_id)
    if rec is None:
        raise HTTPException(404, f"Run {run_id} not found")
    return rec


def append_step(db: Session, run_id: str, step: StepIn) -> RunRecord:
    engine, policy = _require_ready()
    rec = _get_run(db, run_id)
    if rec.status != "running":
        raise HTTPException(409, f"Run {run_id} is {rec.status}; cannot append steps")
    rec.steps.append(_step_record(len(rec.steps), step, utcnow()))
    _refresh_totals(rec)
    agent = db.get(Agent, rec.agent_id)
    a = engine.assess(to_ml_run(rec, agent))
    prev_severity = rec.severity if rec.n_steps > 1 else "healthy"
    _apply_assessment(rec, a)
    rec.risk_trajectory = list(rec.risk_trajectory or []) + [a["risk_score"]]
    step_idx = rec.n_steps - 1
    if rec.first_flag_step is None and a["risk_score"] >= WARN_THRESHOLD:
        rec.first_flag_step = step_idx
    escalated = SEVERITY_RANK[a["severity"]] > SEVERITY_RANK[prev_severity]
    with registry.lock:
        if escalated or not rec.decision:
            _apply_decision(db, rec, a, policy.decide(a), step_idx)
    if step.type == "final_answer":
        rec.status = "completed"
        rec.ended_at = utcnow()
    _finalize_waste(rec)
    db.commit()
    return rec


def finish_run(db: Session, run_id: str) -> RunRecord:
    rec = _get_run(db, run_id)
    if rec.status == "running":
        rec.status = "completed" if rec.has_final_answer else "incomplete"
        rec.ended_at = utcnow()
        _finalize_waste(rec)
        db.commit()
    return rec


# --------------------------------------------------------------------------
# Feedback: closes the loop for both the policy (reward) and the classifier (label)
# --------------------------------------------------------------------------

def record_feedback(db: Session, run_id: str, fb: FeedbackIn) -> Tuple[Feedback, Optional[float]]:
    from ml import CLASSES

    _, policy = _require_ready()
    rec = _get_run(db, run_id)
    if fb.label not in CLASSES:
        raise HTTPException(422, f"label must be one of {CLASSES}")
    action = fb.action_taken or rec.recommended_action
    if action not in ACTIONS:
        raise HTTPException(422, f"action_taken must be one of {ACTIONS}")
    reward = compute_reward(fb.resolved, action, fb.label)

    updated: Optional[float] = None
    if rec.policy_context:
        import numpy as np

        with registry.lock:
            policy.update(np.array(rec.policy_context), action, reward)
            registry.save_policy()
        updated = reward
        ev = (db.query(PolicyEvent).filter(PolicyEvent.run_id == run_id, PolicyEvent.reward.is_(None))
              .order_by(PolicyEvent.id.desc()).first())
        if ev is not None:
            ev.reward = reward
            ev.action = action
            ev.rewarded_at = utcnow()

    row = Feedback(run_id=run_id, label=fb.label, action_taken=action, resolved=fb.resolved, reward=reward,
                   notes=fb.notes, reviewer=fb.reviewer)
    db.add(row)
    db.commit()
    return row, updated
