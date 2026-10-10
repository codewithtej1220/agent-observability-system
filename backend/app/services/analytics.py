"""Read-side aggregations for the dashboard.

Aggregation is done in Python over a time-windowed column projection so the
same code runs on SQLite and PostgreSQL. For very large deployments, move
these into SQL views / a time-series store.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional

import numpy as np
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from ml import CLASSES, FAILURE_TYPES
from ml.bandit import ACTION_LABELS, ACTIONS

from ..orm import Agent, Feedback, PolicyEvent, RunRecord, StepRecord, utcnow
from .registry import registry

FLAGGED = ("warning", "critical")


def _iso(dt: Optional[datetime]) -> Optional[str]:
    """Timestamps are stored as naive UTC; mark them as such for clients."""
    return dt.isoformat() + "Z" if dt else None


def _window(hours: int) -> datetime:
    return utcnow() - timedelta(hours=hours)


def _bucket_size(hours: int) -> timedelta:
    if hours <= 24:
        return timedelta(hours=1)
    if hours <= 24 * 7:
        return timedelta(hours=6)
    return timedelta(days=1)


def _bucket_keys(start: datetime, end: datetime, size: timedelta) -> List[datetime]:
    secs = size.total_seconds()
    first = datetime.fromtimestamp(math.floor(start.timestamp() / secs) * secs)
    keys, k = [], first
    while k <= end:
        keys.append(k)
        k += size
    return keys


def _bucket_of(ts: datetime, size: timedelta) -> datetime:
    secs = size.total_seconds()
    return datetime.fromtimestamp(math.floor(ts.timestamp() / secs) * secs)


def _run_rows(db: Session, since: datetime, agent_id: Optional[str] = None):
    q = db.query(
        RunRecord.id, RunRecord.agent_id, RunRecord.started_at, RunRecord.severity, RunRecord.failure_type,
        RunRecord.input_tokens, RunRecord.output_tokens, RunRecord.cost_usd, RunRecord.avoidable_tokens,
        RunRecord.recommended_action, RunRecord.risk_score, RunRecord.status, RunRecord.n_steps,
        RunRecord.total_latency_ms, RunRecord.has_final_answer, RunRecord.first_flag_step,
    ).filter(RunRecord.started_at >= since)
    if agent_id:
        q = q.filter(RunRecord.agent_id == agent_id)
    return q.all()


def _avoidable_cost(r) -> float:
    total = r.input_tokens + r.output_tokens
    return r.cost_usd * (r.avoidable_tokens / total) if total else 0.0


def _kpis(rows) -> Dict:
    n = len(rows)
    flagged = [r for r in rows if r.severity in FLAGGED]
    tokens = sum(r.input_tokens + r.output_tokens for r in rows)
    first_flags = [r.first_flag_step for r in flagged if r.first_flag_step is not None]
    return {
        "runs": n,
        "flagged": len(flagged),
        "flagged_rate": round(len(flagged) / n, 4) if n else 0.0,
        "critical": sum(1 for r in rows if r.severity == "critical"),
        "tokens": tokens,
        "cost_usd": round(sum(r.cost_usd for r in rows), 2),
        "avoidable_tokens": sum(r.avoidable_tokens for r in rows),
        "avoidable_cost_usd": round(sum(_avoidable_cost(r) for r in rows), 2),
        "success_rate": round(sum(1 for r in rows if r.has_final_answer and r.severity == "healthy") / n, 4) if n else 0.0,
        "avg_risk": round(float(np.mean([r.risk_score for r in rows])), 4) if n else 0.0,
        "median_detection_step": float(np.median(first_flags)) if first_flags else None,
    }


def overview(db: Session, hours: int) -> Dict:
    now = utcnow()
    since = now - timedelta(hours=hours)
    rows = _run_rows(db, since)
    prev = _run_rows(db, since - timedelta(hours=hours))
    prev = [r for r in prev if r.started_at < since]

    size = _bucket_size(hours)
    series = {k: {"runs": 0, "warning": 0, "critical": 0, "tokens": 0, "avoidable_tokens": 0} for k in _bucket_keys(since, now, size)}
    for r in rows:
        b = series.setdefault(_bucket_of(r.started_at, size), {"runs": 0, "warning": 0, "critical": 0, "tokens": 0, "avoidable_tokens": 0})
        b["runs"] += 1
        if r.severity in FLAGGED:
            b[r.severity] += 1
        b["tokens"] += r.input_tokens + r.output_tokens
        b["avoidable_tokens"] += r.avoidable_tokens
    timeseries = [{"t": _iso(k), **v} for k, v in sorted(series.items())]

    failure_counts = Counter(r.failure_type for r in rows if r.severity in FLAGGED and r.failure_type)
    action_counts = Counter(r.recommended_action for r in rows if r.severity in FLAGGED)

    agents = {a.id: a for a in db.query(Agent).all()}
    by_agent: Dict[str, list] = defaultdict(list)
    for r in rows:
        by_agent[r.agent_id].append(r)
    agent_rows = sorted(
        ({"agent_id": a, "name": agents[a].name if a in agents else a, **_kpis(rs)} for a, rs in by_agent.items()),
        key=lambda d: d["flagged_rate"], reverse=True,
    )

    recent = (db.query(RunRecord).filter(RunRecord.severity.in_(FLAGGED))
              .order_by(RunRecord.started_at.desc()).limit(8).all())
    pending_review = (db.query(func.count(RunRecord.id))
                      .filter(RunRecord.severity.in_(FLAGGED), ~RunRecord.feedback.any()).scalar())
    return {
        "hours": hours,
        "kpis": _kpis(rows),
        "previous": _kpis(prev),
        "timeseries": timeseries,
        "bucket_hours": size.total_seconds() / 3600,
        "failure_breakdown": [{"failure_type": k, "count": failure_counts.get(k, 0)} for k in FAILURE_TYPES + ["novel_anomaly"]
                              if failure_counts.get(k, 0) or k != "novel_anomaly"],
        "action_breakdown": [{"action": a, "label": ACTION_LABELS[a], "count": action_counts.get(a, 0)} for a in ACTIONS],
        "agents": agent_rows,
        "recent_alerts": [run_summary(r) for r in recent],
        "pending_review": pending_review,
        "model_version": registry.engine.version if registry.engine else None,
    }


def run_summary(r: RunRecord) -> Dict:
    return {
        "id": r.id,
        "agent_id": r.agent_id,
        "task": r.task,
        "model": r.model,
        "status": r.status,
        "started_at": _iso(r.started_at),
        "n_steps": r.n_steps,
        "tokens": r.input_tokens + r.output_tokens,
        "cost_usd": round(r.cost_usd, 4),
        "risk_score": r.risk_score,
        "severity": r.severity,
        "failure_type": r.failure_type,
        "recommended_action": r.recommended_action,
        "first_flag_step": r.first_flag_step,
        "avoidable_tokens": r.avoidable_tokens,
        "open_set_flag": r.open_set_flag,
    }


def list_runs(db: Session, *, agent_id=None, severity=None, failure_type=None, status=None, q=None,
              hours: Optional[int] = None, sort: str = "recent", limit: int = 50, offset: int = 0) -> Dict:
    query = db.query(RunRecord)
    if agent_id:
        query = query.filter(RunRecord.agent_id == agent_id)
    if severity == "flagged":
        query = query.filter(RunRecord.severity.in_(FLAGGED))
    elif severity:
        query = query.filter(RunRecord.severity == severity)
    if failure_type:
        query = query.filter(RunRecord.failure_type == failure_type)
    if status:
        query = query.filter(RunRecord.status == status)
    if q:
        like = f"%{q}%"
        query = query.filter(RunRecord.task.ilike(like) | RunRecord.id.ilike(like))
    if hours:
        query = query.filter(RunRecord.started_at >= _window(hours))
    total = query.count()
    order = {
        "recent": RunRecord.started_at.desc(),
        "risk": RunRecord.risk_score.desc(),
        "tokens": (RunRecord.input_tokens + RunRecord.output_tokens).desc(),
        "cost": RunRecord.cost_usd.desc(),
    }.get(sort, RunRecord.started_at.desc())
    rows = query.order_by(order).offset(offset).limit(limit).all()
    return {"total": total, "items": [run_summary(r) for r in rows]}


def run_detail(db: Session, run_id: str) -> Optional[Dict]:
    r = (db.query(RunRecord).options(selectinload(RunRecord.steps), selectinload(RunRecord.feedback))
         .filter(RunRecord.id == run_id).first())
    if r is None:
        return None
    agent = db.get(Agent, r.agent_id)
    baseline = None
    if registry.engine and r.agent_id in registry.engine.baselines:
        baseline = registry.engine.baselines[r.agent_id].to_dict()
    cum = 0
    steps = []
    flagged_steps = {i for s in (r.signals or []) for i in s.get("evidence_steps", [])}
    for s in r.steps:
        cum += s.input_tokens + s.output_tokens
        steps.append({
            "index": s.idx, "type": s.type, "tool_name": s.tool_name, "arguments": s.arguments,
            "output": s.output, "status": s.status, "latency_ms": s.latency_ms,
            "input_tokens": s.input_tokens, "output_tokens": s.output_tokens, "cumulative_tokens": cum,
            "timestamp": _iso(s.timestamp),
            "unregistered": bool(agent and agent.registered_tools and s.type == "tool_call"
                                 and s.tool_name not in agent.registered_tools),
            "evidence": s.idx in flagged_steps,
        })
    return {
        **run_summary(r),
        "ended_at": _iso(r.ended_at),
        "input_tokens": r.input_tokens,
        "output_tokens": r.output_tokens,
        "total_latency_ms": r.total_latency_ms,
        "has_final_answer": r.has_final_answer,
        "probabilities": r.probabilities,
        "signals": r.signals,
        "features": r.features,
        "rule_severity": r.rule_severity,
        "novelty_score": r.novelty_score,
        "cluster_id": r.cluster_id,
        "risk_trajectory": r.risk_trajectory,
        "decision": r.decision,
        "model_version": r.model_version,
        "steps": steps,
        "agent": agent_info(agent) if agent else None,
        "baseline": baseline,
        "feedback": [
            {"label": f.label, "action_taken": f.action_taken, "resolved": f.resolved, "reward": round(f.reward, 3),
             "notes": f.notes, "reviewer": f.reviewer, "created_at": _iso(f.created_at)}
            for f in r.feedback
        ],
    }


def agent_info(a: Agent) -> Dict:
    return {"id": a.id, "name": a.name, "description": a.description, "model": a.model,
            "framework": a.framework, "registered_tools": a.registered_tools or []}


def _agent_stats(rows) -> Dict:
    k = _kpis(rows)
    n = len(rows)
    latencies = [r.total_latency_ms for r in rows]
    ftypes = Counter(r.failure_type for r in rows if r.severity in FLAGGED and r.failure_type)
    return {
        **k,
        "avg_steps": round(float(np.mean([r.n_steps for r in rows])), 2) if n else 0.0,
        "avg_tokens": round(k["tokens"] / n) if n else 0,
        "avg_cost_usd": round(k["cost_usd"] / n, 4) if n else 0.0,
        "p95_latency_s": round(float(np.percentile(latencies, 95)) / 1000, 2) if n else 0.0,
        "top_failure": ftypes.most_common(1)[0][0] if ftypes else None,
        "failure_mix": {t: ftypes.get(t, 0) for t in FAILURE_TYPES},
    }


def agents_summary(db: Session, hours: int) -> List[Dict]:
    rows = _run_rows(db, _window(hours))
    by_agent: Dict[str, list] = defaultdict(list)
    for r in rows:
        by_agent[r.agent_id].append(r)
    out = []
    for a in db.query(Agent).order_by(Agent.name).all():
        out.append({**agent_info(a), **_agent_stats(by_agent.get(a.id, []))})
    return out


def tool_graph(db: Session, agent_id: str, hours: int, max_runs: int = 400) -> Dict:
    """Transition graph of what this agent actually does: START -> tools -> END."""
    runs = (db.query(RunRecord.id, RunRecord.severity).filter(RunRecord.agent_id == agent_id,
            RunRecord.started_at >= _window(hours)).order_by(RunRecord.started_at.desc()).limit(max_runs).all())
    if not runs:
        return {"nodes": [], "edges": [], "runs": 0}
    sev = {r.id: r.severity for r in runs}
    steps = (db.query(StepRecord.run_id, StepRecord.idx, StepRecord.type, StepRecord.tool_name, StepRecord.status,
                      StepRecord.latency_ms)
             .filter(StepRecord.run_id.in_(list(sev))).order_by(StepRecord.run_id, StepRecord.idx).all())
    agent = db.get(Agent, agent_id)
    registered = set(agent.registered_tools or []) if agent else set()

    def node_of(s) -> str:
        if s.type == "final_answer":
            return "END"
        if s.type == "llm":
            return "reasoning"
        return s.tool_name or "?"

    nodes: Dict[str, Dict] = defaultdict(lambda: {"calls": 0, "errors": 0, "latency": 0.0, "flagged_calls": 0, "positions": []})
    edges: Dict[tuple, Dict] = defaultdict(lambda: {"count": 0, "flagged": 0})
    by_run: Dict[str, list] = defaultdict(list)
    for s in steps:
        by_run[s.run_id].append(s)
    for run_id, ss in by_run.items():
        flagged = sev[run_id] in FLAGGED
        prev = "START"
        nodes["START"]["calls"] += 1
        for s in ss:
            n = node_of(s)
            nd = nodes[n]
            nd["calls"] += 1
            nd["errors"] += s.status == "error"
            nd["latency"] += s.latency_ms
            nd["flagged_calls"] += flagged
            nd["positions"].append(s.idx + 1)
            e = edges[(prev, n)]
            e["count"] += 1
            e["flagged"] += flagged
            prev = n
        if prev != "END":
            e = edges[(prev, "INCOMPLETE")]
            e["count"] += 1
            e["flagged"] += flagged
            nodes["INCOMPLETE"]["calls"] += 1
            nodes["INCOMPLETE"]["positions"].append(len(ss) + 1)
    node_list = []
    for name, d in nodes.items():
        kind = ("terminal" if name in ("START", "END", "INCOMPLETE") else "reasoning" if name == "reasoning"
                else "tool" if not registered or name in registered else "unregistered")
        node_list.append({
            "id": name, "kind": kind, "calls": d["calls"],
            "error_rate": round(d["errors"] / d["calls"], 4) if d["calls"] else 0.0,
            "avg_latency_ms": round(d["latency"] / d["calls"], 1) if d["calls"] and kind != "terminal" else None,
            "flagged_share": round(d["flagged_calls"] / d["calls"], 4) if d["calls"] and kind != "terminal" else None,
            "avg_position": 0.0 if name == "START" else round(float(np.median(d["positions"])), 2) if d["positions"] else 0.0,
        })
    edge_list = [{"source": s, "target": t, "count": d["count"], "flagged_share": round(d["flagged"] / d["count"], 4)}
                 for (s, t), d in edges.items()]
    return {"nodes": node_list, "edges": edge_list, "runs": len(by_run)}


def agent_detail(db: Session, agent_id: str, hours: int) -> Optional[Dict]:
    a = db.get(Agent, agent_id)
    if a is None:
        return None
    now = utcnow()
    since = now - timedelta(hours=hours)
    rows = _run_rows(db, since, agent_id)
    size = _bucket_size(hours)
    series = {k: [] for k in _bucket_keys(since, now, size)}
    for r in rows:
        series.setdefault(_bucket_of(r.started_at, size), []).append(r)
    timeseries = []
    for k, rs in sorted(series.items()):
        n = len(rs)
        timeseries.append({
            "t": _iso(k), "runs": n,
            "flagged": sum(1 for r in rs if r.severity in FLAGGED),
            "avg_tokens": round(sum(r.input_tokens + r.output_tokens for r in rs) / n) if n else 0,
            "avg_risk": round(float(np.mean([r.risk_score for r in rs])), 4) if n else None,
        })
    baseline = registry.engine.baselines.get(agent_id).to_dict() if registry.engine and agent_id in registry.engine.baselines else None
    graph = tool_graph(db, agent_id, hours)
    return {
        **agent_info(a),
        "stats": _agent_stats(rows),
        "baseline": baseline,
        "timeseries": timeseries,
        "tool_graph": graph,
        "tools": sorted((n for n in graph["nodes"] if n["kind"] in ("tool", "unregistered", "reasoning")),
                        key=lambda n: n["calls"], reverse=True),
    }


def compare_agents(db: Session, ids: Iterable[str], hours: int) -> Dict:
    ids = [i for i in ids if i]
    now = utcnow()
    since = now - timedelta(hours=hours)
    size = _bucket_size(hours) if hours > 24 else timedelta(hours=3)
    keys = _bucket_keys(since, now, size)
    summaries, series = [], {k: {"t": _iso(k)} for k in keys}
    for agent_id in ids:
        a = db.get(Agent, agent_id)
        if a is None:
            continue
        rows = _run_rows(db, since, agent_id)
        summaries.append({**agent_info(a), **_agent_stats(rows)})
        grouped: Dict[datetime, list] = defaultdict(list)
        for r in rows:
            grouped[_bucket_of(r.started_at, size)].append(r)
        for k in keys:
            rs = grouped.get(k, [])
            series[k][agent_id] = round(sum(1 for r in rs if r.severity in FLAGGED) / len(rs), 4) if rs else None
    return {"agents": summaries, "flag_rate_series": [series[k] for k in keys]}


def _uncertainty(probs: Dict[str, float]) -> float:
    p = np.array([probs.get(c, 0.0) for c in CLASSES]) + 1e-12
    return float(-(p * np.log(p)).sum() / math.log(len(CLASSES)))


def review_queue(db: Session, sort: str = "uncertainty", limit: int = 50, agent_id: Optional[str] = None) -> Dict:
    """Flagged runs awaiting a human label.

    sort="uncertainty" is active learning: runs the classifier is least sure
    about come first, because those labels improve the model the most.
    """
    q = db.query(RunRecord).filter(RunRecord.severity.in_(FLAGGED), ~RunRecord.feedback.any())
    if agent_id:
        q = q.filter(RunRecord.agent_id == agent_id)
    rows = q.order_by(RunRecord.started_at.desc()).limit(2000).all()
    items = [{**run_summary(r), "uncertainty": round(_uncertainty(r.probabilities or {}), 4)} for r in rows]
    if sort == "uncertainty":
        items.sort(key=lambda d: d["uncertainty"], reverse=True)
    elif sort == "risk":
        items.sort(key=lambda d: d["risk_score"], reverse=True)
    labeled = db.query(func.count(Feedback.id)).scalar()
    unused = db.query(func.count(Feedback.id)).filter(Feedback.used_in_version.is_(None)).scalar()
    return {"total": len(items), "items": items[:limit], "labels_total": labeled, "labels_not_yet_trained": unused}


def behavior_map(db: Session, limit: int = 800) -> Dict:
    rows = (db.query(RunRecord.id, RunRecord.agent_id, RunRecord.coords, RunRecord.cluster_id, RunRecord.severity,
                     RunRecord.failure_type, RunRecord.risk_score)
            .order_by(RunRecord.started_at.desc()).limit(limit).all())
    clusters = registry.engine.unsupervised.clusters if registry.engine else []
    return {
        "points": [{"id": r.id, "agent_id": r.agent_id, "x": r.coords[0], "y": r.coords[1], "cluster": r.cluster_id,
                    "severity": r.severity, "failure_type": r.failure_type, "risk": r.risk_score}
                   for r in rows if r.coords and len(r.coords) == 2],
        "clusters": clusters,
    }


def policy_analytics(db: Session) -> Dict:
    events = db.query(PolicyEvent).order_by(PolicyEvent.created_at).all()
    rewarded = [e for e in events if e.reward is not None]
    by_day: Dict[str, List[float]] = defaultdict(list)
    for e in rewarded:
        by_day[e.created_at.date().isoformat()].append(e.reward)
    daily = [{"date": d, "avg_reward": round(float(np.mean(v)), 4), "n": len(v)} for d, v in sorted(by_day.items())]

    mix: Dict[str, Counter] = defaultdict(Counter)
    for e in events:
        mix[e.failure_type or "unknown"][e.action] += 1
    types = [t for t in FAILURE_TYPES + ["novel_anomaly", "unknown"] if t in mix]
    reward_by_action: Dict[str, List[float]] = defaultdict(list)
    for e in rewarded:
        reward_by_action[e.action].append(e.reward)
    return {
        "policy": registry.policy.summary() if registry.policy else None,
        "warm_start": registry.warmstart_report(),
        "live": {
            "decisions": len(events),
            "rewarded": len(rewarded),
            "avg_reward": round(float(np.mean([e.reward for e in rewarded])), 4) if rewarded else None,
            "daily_reward": daily,
            "action_by_failure": {"types": types, "actions": ACTIONS,
                                  "matrix": [[mix[t].get(a, 0) for a in ACTIONS] for t in types]},
            "reward_by_action": [
                {"action": a, "label": ACTION_LABELS[a], "n": len(reward_by_action.get(a, [])),
                 "avg_reward": round(float(np.mean(reward_by_action[a])), 4) if reward_by_action.get(a) else None}
                for a in ACTIONS
            ],
        },
    }
