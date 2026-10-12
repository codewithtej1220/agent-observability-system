"""Dashboard API for LLM monitoring."""
from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from datetime import timedelta
from typing import Any, Dict, List, Literal, Optional

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .auth import Ctx, require_access, role
from .config import get_settings
from .db import get_db
from .llm import alerts as alerts_mod
from .llm.alerts import APP_SOURCES
from .llm.checks import RULE_TYPES, SCRIPTS, CheckInput, redact, validate_rules
from .llm.drift import latest_run, run_test
from .llm.evaluator import evaluate
from .llm.judge import DEFAULT_JUDGE_MODELS
from .llm.providers import get_adapter
from .llm.upstream import call_json, credential_key, resolve_credential
from .orm import PROVIDERS, ProviderCredential, utcnow
from .orm_llm import EVENT_METRICS, WINDOW_METRICS, AlertEvent, AlertRule, Contract, DriftRun, DriftTest, LLMCall
from .services.analytics import _bucket_keys, _bucket_of, _bucket_size, _iso

router = APIRouter(prefix="/api")
member = role("member")


def _p(values: List[float], q: float) -> Optional[float]:
    return round(float(np.percentile(values, q)), 1) if values else None


def _rate(num: int, den: int) -> Optional[float]:
    return round(num / den, 4) if den else None


def _mean(values: List[float]) -> Optional[float]:
    return round(float(np.mean(values)), 4) if values else None


# =========================================================================== overview
def _stats(calls: List[LLMCall]) -> Dict[str, Any]:
    n = len(calls)
    lat = [c.latency_ms for c in calls if c.status_code < 400]
    return {
        "calls": n,
        "error_rate": _rate(sum(c.status_code >= 400 and c.enforcement_action != "blocked" for c in calls), n),
        "violation_rate": _rate(sum(c.violations > 0 for c in calls), n),
        "adherence": _mean([c.adherence for c in calls if c.adherence is not None]),
        "judge_score": _mean([c.judge_score for c in calls if c.judge_score is not None]),
        "p50_latency_ms": _p(lat, 50),
        "p95_latency_ms": _p(lat, 95),
        "avg_ttft_ms": _mean([c.ttft_ms for c in calls if c.ttft_ms]),
        "input_tokens": sum(c.input_tokens for c in calls),
        "output_tokens": sum(c.output_tokens for c in calls),
        "cost_usd": round(sum(c.cost_usd for c in calls), 4),
        "judge_cost_usd": round(sum(c.judge_cost_usd for c in calls), 4),
        "blocked": sum(c.enforcement_action == "blocked" for c in calls),
        "repaired": sum(c.enforcement_action in ("repaired", "fallback") for c in calls),
        "pii": sum(c.pii_flag for c in calls),
        "injection": sum(c.injection_flag for c in calls),
        "critical": sum(c.severity == "critical" for c in calls),
    }


def call_summary(c: LLMCall, contracts: Dict[int, str]) -> Dict[str, Any]:
    failed = [x["label"] for x in c.checks if not x.get("passed", True) and not x.get("skipped")]
    return {
        "id": c.id, "created_at": _iso(c.created_at), "provider": c.provider, "model": c.model,
        "contract": contracts.get(c.contract_id), "contract_id": c.contract_id, "source": c.source,
        "status_code": c.status_code, "latency_ms": c.latency_ms, "streamed": c.streamed,
        "input_tokens": c.input_tokens, "output_tokens": c.output_tokens, "cost_usd": c.cost_usd,
        "severity": c.severity, "violations": c.violations, "adherence": c.adherence, "judge_score": c.judge_score,
        "enforcement_action": c.enforcement_action, "failed_checks": failed[:5],
        "preview": (c.last_user or "")[:160], "session_id": c.session_id, "end_user": c.end_user, "tags": c.tags,
    }


def _contract_names(db: Session, ws: int) -> Dict[int, str]:
    return {c.id: c.name for c in db.query(Contract.id, Contract.name).filter(Contract.workspace_id == ws)}


@router.get("/llm/overview", tags=["llm"])
def llm_overview(hours: int = Query(24, ge=1, le=24 * 90), ctx: Ctx = Depends(require_access),
                 db: Session = Depends(get_db)):
    ws = ctx.workspace_id
    now = utcnow()
    since = now - timedelta(hours=hours)
    calls = (db.query(LLMCall).filter(LLMCall.workspace_id == ws, LLMCall.created_at >= since,
                                      LLMCall.source.in_(APP_SOURCES)).all())
    prev = (db.query(LLMCall).filter(LLMCall.workspace_id == ws, LLMCall.source.in_(APP_SOURCES),
                                     LLMCall.created_at >= since - timedelta(hours=hours),
                                     LLMCall.created_at < since).all())
    size = _bucket_size(hours)
    buckets = {k: [] for k in _bucket_keys(since, now, size)}
    for c in calls:
        buckets.setdefault(_bucket_of(c.created_at, size), []).append(c)
    series = [{"t": _iso(k), "calls": len(v), "violations": sum(c.violations > 0 for c in v),
               "errors": sum(c.status_code >= 400 and c.enforcement_action != "blocked" for c in v),
               "blocked": sum(c.enforcement_action == "blocked" for c in v),
               "p95_latency_ms": _p([c.latency_ms for c in v if c.status_code < 400], 95)}
              for k, v in sorted(buckets.items())]

    by_model: Dict[tuple, list] = defaultdict(list)
    by_contract: Dict[Optional[int], list] = defaultdict(list)
    failed: Counter = Counter()
    for c in calls:
        by_model[(c.provider, c.model)].append(c)
        by_contract[c.contract_id].append(c)
        for x in c.checks:
            if not x.get("passed", True) and not x.get("skipped"):
                failed[(x["rule_id"], x["label"], x.get("source", ""))] += 1
    names = _contract_names(db, ws)
    contracts = {c.id: c for c in db.query(Contract).filter(Contract.workspace_id == ws)}
    open_alerts = db.query(AlertEvent).filter(AlertEvent.workspace_id == ws, AlertEvent.status == "open").count()
    issues = sorted([c for c in calls if c.severity != "ok"], key=lambda c: c.created_at, reverse=True)[:8]
    return {
        "hours": hours,
        "bucket_hours": size.total_seconds() / 3600,
        "kpis": {**_stats(calls), "open_alerts": open_alerts},
        "previous": _stats(prev),
        "timeseries": series,
        "by_model": sorted(({"provider": p, "model": m, **_stats(v)} for (p, m), v in by_model.items()),
                           key=lambda d: d["calls"], reverse=True),
        "by_contract": [{"contract_id": cid, "name": names.get(cid, "No contract"),
                         "mode": contracts[cid].mode if cid in contracts else None, **_stats(v)}
                        for cid, v in sorted(by_contract.items(), key=lambda kv: -len(kv[1]))],
        "top_failed_checks": [{"rule_id": r, "label": l, "source": s, "count": n} for (r, l, s), n in failed.most_common(10)],
        "recent_issues": [call_summary(c, names) for c in issues],
    }


# =========================================================================== calls
@router.get("/llm/calls", tags=["llm"])
def list_calls(provider: Optional[str] = None, model: Optional[str] = None, contract_id: Optional[int] = None,
               severity: Optional[str] = None, enforcement: Optional[str] = None, source: str = "apps",
               q: Optional[str] = None, session_id: Optional[str] = None,
               limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
               ctx: Ctx = Depends(require_access), db: Session = Depends(get_db)):
    query = db.query(LLMCall).filter(LLMCall.workspace_id == ctx.workspace_id)
    if source == "apps":
        query = query.filter(LLMCall.source.in_(APP_SOURCES))
    elif source != "all":
        query = query.filter(LLMCall.source == source)
    for col, val in ((LLMCall.provider, provider), (LLMCall.model, model), (LLMCall.contract_id, contract_id),
                     (LLMCall.enforcement_action, enforcement), (LLMCall.session_id, session_id)):
        if val not in (None, ""):
            query = query.filter(col == val)
    if severity == "issues":
        query = query.filter(LLMCall.severity != "ok")
    elif severity:
        query = query.filter(LLMCall.severity == severity)
    if q:
        like = f"%{q}%"
        query = query.filter(LLMCall.last_user.ilike(like) | LLMCall.response_text.ilike(like) | LLMCall.id.ilike(like))
    total = query.count()
    rows = query.order_by(LLMCall.created_at.desc()).offset(offset).limit(limit).all()
    names = _contract_names(db, ctx.workspace_id)
    models = sorted({(p, m) for p, m in db.query(LLMCall.provider, LLMCall.model)
                     .filter(LLMCall.workspace_id == ctx.workspace_id).distinct()})
    return {"total": total, "items": [call_summary(c, names) for c in rows],
            "models": [{"provider": p, "model": m} for p, m in models]}


@router.get("/llm/calls/{call_id}", tags=["llm"])
def get_call(call_id: str, ctx: Ctx = Depends(require_access), db: Session = Depends(get_db)):
    c = db.get(LLMCall, call_id)
    if c is None or c.workspace_id != ctx.workspace_id:
        raise HTTPException(404, "Call not found")
    names = _contract_names(db, ctx.workspace_id)
    return {**call_summary(c, names), "endpoint": c.endpoint, "error": c.error, "ttft_ms": c.ttft_ms,
            "system_prompt": c.system_prompt, "last_user": c.last_user, "n_messages": c.n_messages,
            "response_text": c.response_text, "content_stored": c.content_stored, "finish_reason": c.finish_reason,
            "usage_estimated": c.usage_estimated, "judge_cost_usd": c.judge_cost_usd, "relevance": c.relevance,
            "pii_flag": c.pii_flag, "injection_flag": c.injection_flag, "checks": c.checks, "attempts": c.attempts}


# =========================================================================== browser extension
BROWSER_APPS = {"gemini-web": "gemini", "chatgpt-web": "openai", "claude-web": "anthropic"}
_TURN_NS = uuid.UUID("6f1d3c52-8d0e-4c43-9a51-2f6b5e0f7a11")


class BrowserTurnIn(BaseModel):
    app: Literal["gemini-web", "chatgpt-web", "claude-web"]
    turn_id: str = Field(min_length=1, max_length=200)
    conversation_id: str = Field("", max_length=200)
    user_message: str = Field("", max_length=100_000)
    response: str = Field(min_length=1, max_length=200_000)
    model: str = Field("", max_length=120)
    project: Optional[str] = Field(None, max_length=64)


@router.post("/llm/ingest/browser-turn", tags=["llm"])
async def ingest_browser_turn(body: BrowserTurnIn, ctx: Ctx = Depends(member), db: Session = Depends(get_db)):
    """One finished prompt/answer pair from a consumer chat site, sent by the browser extension.

    Idempotent per (workspace, app, turn_id): a regenerated answer updates the same call.
    Monitoring only: the answer is already on the user's screen.
    """
    from .llm.providers import estimate_tokens

    ws = ctx.workspace
    contract = None
    if body.project:
        contract = db.query(Contract).filter(Contract.workspace_id == ws.id, Contract.slug == body.project,
                                             Contract.active.is_(True)).first()
    ev = await evaluate(db, ws, contract, CheckInput("", body.user_message, body.response))
    call_id = str(uuid.uuid5(_TURN_NS, f"{ws.id}:{body.app}:{body.turn_id}"))
    store, red = bool(ws.setting("store_content")), bool(ws.setting("redact_pii"))

    def keep(t: str) -> str:
        return (redact(t) if red else t)[:100_000] if store else ""

    call = db.get(LLMCall, call_id)
    is_new = call is None
    if is_new:
        call = LLMCall(id=call_id, workspace_id=ws.id, created_at=utcnow())
        db.add(call)
    call.provider, call.model, call.endpoint = BROWSER_APPS[body.app], body.model or body.app, body.app
    call.source, call.session_id, call.tags = "browser", body.conversation_id, [body.app]
    call.contract_id = contract.id if contract else None
    call.status_code, call.error, call.streamed, call.latency_ms = 200, "", True, 0.0
    call.system_prompt, call.last_user, call.response_text = "", keep(body.user_message), keep(body.response)
    call.content_stored, call.n_messages, call.finish_reason = store, 1, None
    call.input_tokens, call.output_tokens = estimate_tokens(body.user_message), estimate_tokens(body.response)
    call.usage_estimated, call.cost_usd = True, 0.0  # consumer apps are not billed per token
    call.eval_status, call.checks, call.violations = "done", [c.to_dict() for c in ev.checks], len(ev.violations)
    call.adherence, call.judge_score, call.judge_cost_usd = ev.adherence, ev.judge_score, round(ev.judge_cost, 6)
    call.relevance, call.severity = ev.relevance, ev.severity
    call.pii_flag, call.injection_flag = ev.has("pii_output"), ev.has("prompt_injection")
    db.commit()
    if is_new:
        await alerts_mod.on_call_evaluated(db, ws, call)
    failed = [c.label for c in ev.checks if not c.passed and not c.skipped and c.severity != "info"]
    return {"call_id": call_id, "new": is_new, "severity": ev.severity, "failed": failed,
            "contract": contract.slug if contract else None,
            "url": f"{get_settings().public_url.rstrip('/')}/llm/calls/{call_id}"}


# =========================================================================== contracts
class ContractIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    description: str = ""
    rules: List[Dict[str, Any]] = []
    mode: Literal["monitor", "block", "repair"] = "monitor"
    max_repairs: int = Field(1, ge=0, le=3)
    fallback_models: List[str] = []
    judge_in_enforcement: bool = False
    active: bool = True


def _contract_out(c: Contract) -> Dict[str, Any]:
    return {"id": c.id, "name": c.name, "slug": c.slug, "description": c.description, "rules": c.rules,
            "mode": c.mode, "max_repairs": c.max_repairs, "fallback_models": c.fallback_models,
            "judge_in_enforcement": c.judge_in_enforcement, "active": c.active,
            "created_at": _iso(c.created_at), "updated_at": _iso(c.updated_at)}


@router.get("/llm/rule-types", tags=["llm"])
def rule_types(ctx: Ctx = Depends(require_access)):
    return {"types": [{"type": k, "label": v["label"], "params": v["params"]} for k, v in RULE_TYPES.items()],
            "scripts": list(SCRIPTS)}


@router.get("/llm/contracts", tags=["llm"])
def list_contracts(ctx: Ctx = Depends(require_access), db: Session = Depends(get_db)):
    rows = db.query(Contract).filter(Contract.workspace_id == ctx.workspace_id).order_by(Contract.name).all()
    since = utcnow() - timedelta(days=7)
    stats = defaultdict(list)
    for c in db.query(LLMCall).filter(LLMCall.workspace_id == ctx.workspace_id, LLMCall.created_at >= since,
                                      LLMCall.contract_id.isnot(None)).all():
        stats[c.contract_id].append(c)
    return [{**_contract_out(c), "stats_7d": _stats(stats.get(c.id, []))} for c in rows]


def _apply_contract(c: Contract, body: ContractIn) -> None:
    try:
        rules = validate_rules(body.rules)
    except (ValueError, TypeError) as e:
        raise HTTPException(422, str(e)) from e
    c.name, c.slug, c.description = body.name.strip(), body.slug, body.description
    c.rules, c.mode, c.max_repairs = rules, body.mode, body.max_repairs
    c.fallback_models = [m.strip() for m in body.fallback_models if m.strip()][:3]
    c.judge_in_enforcement, c.active = body.judge_in_enforcement, body.active


@router.post("/llm/contracts", tags=["llm"])
def create_contract(body: ContractIn, ctx: Ctx = Depends(member), db: Session = Depends(get_db)):
    if db.query(Contract).filter(Contract.workspace_id == ctx.workspace_id, Contract.slug == body.slug).first():
        raise HTTPException(409, f"A contract with slug '{body.slug}' already exists")
    c = Contract(workspace_id=ctx.workspace_id)
    _apply_contract(c, body)
    db.add(c)
    db.commit()
    return _contract_out(c)


def _get_contract(db: Session, ctx: Ctx, cid: int) -> Contract:
    c = db.get(Contract, cid)
    if c is None or c.workspace_id != ctx.workspace_id:
        raise HTTPException(404, "Contract not found")
    return c


@router.get("/llm/contracts/{cid}", tags=["llm"])
def get_contract(cid: int, ctx: Ctx = Depends(require_access), db: Session = Depends(get_db)):
    return _contract_out(_get_contract(db, ctx, cid))


@router.patch("/llm/contracts/{cid}", tags=["llm"])
def update_contract(cid: int, body: ContractIn, ctx: Ctx = Depends(member), db: Session = Depends(get_db)):
    c = _get_contract(db, ctx, cid)
    clash = db.query(Contract).filter(Contract.workspace_id == ctx.workspace_id, Contract.slug == body.slug,
                                      Contract.id != cid).first()
    if clash:
        raise HTTPException(409, f"A contract with slug '{body.slug}' already exists")
    _apply_contract(c, body)
    db.commit()
    return _contract_out(c)


@router.delete("/llm/contracts/{cid}", tags=["llm"])
def delete_contract(cid: int, ctx: Ctx = Depends(member), db: Session = Depends(get_db)):
    db.delete(_get_contract(db, ctx, cid))
    db.commit()
    return {"ok": True}


class ContractTestIn(BaseModel):
    rules: List[Dict[str, Any]]
    system: str = ""
    user: str = ""
    response: str
    use_judge: bool = False


@router.post("/llm/contracts/test", tags=["llm"])
async def test_contract(body: ContractTestIn, ctx: Ctx = Depends(member), db: Session = Depends(get_db)):
    """Dry-run rules against a sample exchange (nothing is stored)."""
    try:
        rules = validate_rules(body.rules)
    except (ValueError, TypeError) as e:
        raise HTTPException(422, str(e)) from e
    tmp = Contract(workspace_id=ctx.workspace_id, name="test", slug="test", rules=rules, active=True)
    ev = await evaluate(db, ctx.workspace, tmp, CheckInput(body.system, body.user, body.response),
                        use_judge=body.use_judge)
    return {"checks": [c.to_dict() for c in ev.checks], "adherence": ev.adherence, "severity": ev.severity,
            "would_block": bool(ev.critical_violations), "judge_cost_usd": ev.judge_cost}


# =========================================================================== alerts
class AlertRuleIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    metric: str
    comparison: Literal[">", "<"] = ">"
    threshold: float = 0.0
    window_minutes: int = Field(60, ge=5, le=24 * 60 * 7)
    min_calls: int = Field(10, ge=1, le=100000)
    scope: Dict[str, Any] = {}
    channels: Dict[str, Any] = {}
    cooldown_minutes: int = Field(30, ge=0, le=24 * 60)
    enabled: bool = True


def _rule_out(r: AlertRule) -> Dict[str, Any]:
    return {"id": r.id, "name": r.name, "metric": r.metric, "metric_label": alerts_mod.METRIC_LABELS[r.metric],
            "comparison": r.comparison, "threshold": r.threshold, "window_minutes": r.window_minutes,
            "min_calls": r.min_calls, "scope": r.scope, "channels": r.channels, "cooldown_minutes": r.cooldown_minutes,
            "enabled": r.enabled, "last_fired_at": _iso(r.last_fired_at), "kind": "event" if r.metric in EVENT_METRICS else "window"}


@router.get("/llm/alert-metrics", tags=["alerts"])
def alert_metrics(ctx: Ctx = Depends(require_access)):
    return {"window": [{"id": m, "label": alerts_mod.METRIC_LABELS[m]} for m in WINDOW_METRICS],
            "event": [{"id": m, "label": alerts_mod.METRIC_LABELS[m]} for m in EVENT_METRICS],
            "email_enabled": bool(get_settings().smtp_host)}


@router.get("/llm/alert-rules", tags=["alerts"])
def list_rules(ctx: Ctx = Depends(require_access), db: Session = Depends(get_db)):
    return [_rule_out(r) for r in db.query(AlertRule).filter(AlertRule.workspace_id == ctx.workspace_id).order_by(AlertRule.id)]


def _apply_rule(r: AlertRule, body: AlertRuleIn) -> None:
    try:
        channels = alerts_mod.validate_rule(body.metric, body.comparison, body.channels)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    r.name, r.metric, r.comparison, r.threshold = body.name, body.metric, body.comparison, body.threshold
    r.window_minutes, r.min_calls, r.cooldown_minutes, r.enabled = body.window_minutes, body.min_calls, body.cooldown_minutes, body.enabled
    r.scope = {k: v for k, v in body.scope.items() if k in ("provider", "model", "contract_id") and v not in (None, "")}
    r.channels = channels


@router.post("/llm/alert-rules", tags=["alerts"])
def create_rule(body: AlertRuleIn, ctx: Ctx = Depends(member), db: Session = Depends(get_db)):
    r = AlertRule(workspace_id=ctx.workspace_id)
    _apply_rule(r, body)
    db.add(r)
    db.commit()
    return _rule_out(r)


def _get_rule(db, ctx, rid) -> AlertRule:
    r = db.get(AlertRule, rid)
    if r is None or r.workspace_id != ctx.workspace_id:
        raise HTTPException(404, "Alert rule not found")
    return r


@router.patch("/llm/alert-rules/{rid}", tags=["alerts"])
def update_rule(rid: int, body: AlertRuleIn, ctx: Ctx = Depends(member), db: Session = Depends(get_db)):
    r = _get_rule(db, ctx, rid)
    _apply_rule(r, body)
    db.commit()
    return _rule_out(r)


@router.delete("/llm/alert-rules/{rid}", tags=["alerts"])
def delete_rule(rid: int, ctx: Ctx = Depends(member), db: Session = Depends(get_db)):
    db.delete(_get_rule(db, ctx, rid))
    db.commit()
    return {"ok": True}


@router.post("/llm/alert-rules/{rid}/test", tags=["alerts"])
async def test_rule(rid: int, ctx: Ctx = Depends(member), db: Session = Depends(get_db)):
    """Send a test notification through the rule's channels."""
    r = _get_rule(db, ctx, rid)
    ev = await alerts_mod.fire(db, ctx.workspace_id, r, f"Test alert: {r.name}",
                               "This is a test notification from Agent Observability.", "info", ref_type="test")
    ev.status = "resolved"
    db.commit()
    return {"notified": ev.notified}


@router.get("/llm/alerts", tags=["alerts"])
def list_alerts(status: Optional[str] = None, limit: int = Query(100, ge=1, le=500),
                ctx: Ctx = Depends(require_access), db: Session = Depends(get_db)):
    q = db.query(AlertEvent).filter(AlertEvent.workspace_id == ctx.workspace_id)
    if status:
        q = q.filter(AlertEvent.status == status)
    rows = q.order_by(AlertEvent.id.desc()).limit(limit).all()
    return [{"id": e.id, "rule_id": e.rule_id, "title": e.title, "message": e.message, "severity": e.severity,
             "value": e.value, "ref_type": e.ref_type, "ref_id": e.ref_id, "status": e.status,
             "created_at": _iso(e.created_at), "resolved_at": _iso(e.resolved_at), "notified": e.notified}
            for e in rows]


class AlertStatusIn(BaseModel):
    status: Literal["open", "acknowledged", "resolved"]


@router.patch("/llm/alerts/{eid}", tags=["alerts"])
def set_alert_status(eid: int, body: AlertStatusIn, ctx: Ctx = Depends(member), db: Session = Depends(get_db)):
    e = db.get(AlertEvent, eid)
    if e is None or e.workspace_id != ctx.workspace_id:
        raise HTTPException(404, "Alert not found")
    e.status = body.status
    e.resolved_at = utcnow() if body.status == "resolved" else None
    db.commit()
    return {"ok": True}


# =========================================================================== drift tests
class DriftTestIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    provider: Literal["openai", "anthropic", "gemini"]
    model: str = Field(min_length=1, max_length=120)
    credential_id: Optional[int] = None
    system_prompt: str = ""
    prompt: str = Field(min_length=1, max_length=20000)
    contract_id: Optional[int] = None
    similarity_threshold: float = Field(0.5, ge=0, le=1)
    interval_minutes: int = Field(360, ge=15, le=7 * 24 * 60)
    enabled: bool = True


def _test_out(db: Session, t: DriftTest) -> Dict[str, Any]:
    last = latest_run(db, t.id)
    return {"id": t.id, "name": t.name, "provider": t.provider, "model": t.model, "credential_id": t.credential_id,
            "system_prompt": t.system_prompt, "prompt": t.prompt, "contract_id": t.contract_id,
            "baseline_text": t.baseline_text, "similarity_threshold": t.similarity_threshold,
            "interval_minutes": t.interval_minutes, "enabled": t.enabled, "last_run_at": _iso(t.last_run_at),
            "last_status": t.last_status, "last_similarity": last.similarity if last else None}


@router.get("/llm/drift-tests", tags=["drift"])
def list_tests(ctx: Ctx = Depends(require_access), db: Session = Depends(get_db)):
    return [_test_out(db, t) for t in db.query(DriftTest).filter(DriftTest.workspace_id == ctx.workspace_id).order_by(DriftTest.name)]


def _apply_test(db: Session, ctx: Ctx, t: DriftTest, body: DriftTestIn) -> None:
    if body.credential_id is not None:
        cred = db.get(ProviderCredential, body.credential_id)
        if cred is None or cred.workspace_id != ctx.workspace_id or cred.provider != body.provider:
            raise HTTPException(422, "Credential must belong to this workspace and match the provider")
    if body.contract_id is not None:
        _get_contract(db, ctx, body.contract_id)
    changed_prompt = (t.prompt, t.system_prompt, t.model, t.provider) != (body.prompt, body.system_prompt, body.model, body.provider)
    for k, v in body.model_dump().items():
        setattr(t, k, v)
    if changed_prompt:
        t.baseline_text = ""  # new prompt or model: re-baseline on next run


@router.post("/llm/drift-tests", tags=["drift"])
def create_test(body: DriftTestIn, ctx: Ctx = Depends(member), db: Session = Depends(get_db)):
    t = DriftTest(workspace_id=ctx.workspace_id, prompt="")
    _apply_test(db, ctx, t, body)
    db.add(t)
    db.commit()
    return _test_out(db, t)


def _get_test(db, ctx, tid) -> DriftTest:
    t = db.get(DriftTest, tid)
    if t is None or t.workspace_id != ctx.workspace_id:
        raise HTTPException(404, "Drift test not found")
    return t


@router.patch("/llm/drift-tests/{tid}", tags=["drift"])
def update_test(tid: int, body: DriftTestIn, ctx: Ctx = Depends(member), db: Session = Depends(get_db)):
    t = _get_test(db, ctx, tid)
    _apply_test(db, ctx, t, body)
    db.commit()
    return _test_out(db, t)


@router.delete("/llm/drift-tests/{tid}", tags=["drift"])
def delete_test(tid: int, ctx: Ctx = Depends(member), db: Session = Depends(get_db)):
    db.delete(_get_test(db, ctx, tid))
    db.commit()
    return {"ok": True}


@router.post("/llm/drift-tests/{tid}/run", tags=["drift"])
async def run_now(tid: int, ctx: Ctx = Depends(member), db: Session = Depends(get_db)):
    run = await run_test(db, _get_test(db, ctx, tid))
    return {"status": run.status, "similarity": run.similarity, "detail": run.detail}


@router.get("/llm/drift-tests/{tid}/runs", tags=["drift"])
def test_runs(tid: int, ctx: Ctx = Depends(require_access), db: Session = Depends(get_db)):
    t = _get_test(db, ctx, tid)
    rows = db.query(DriftRun).filter(DriftRun.test_id == t.id).order_by(DriftRun.id.desc()).limit(100).all()
    return [{"id": r.id, "ran_at": _iso(r.ran_at), "status": r.status, "similarity": r.similarity,
             "violations": r.violations, "latency_ms": r.latency_ms, "output_tokens": r.output_tokens,
             "response_text": r.response_text, "detail": r.detail} for r in rows]


@router.post("/llm/drift-tests/{tid}/baseline/{run_id}", tags=["drift"])
def set_baseline(tid: int, run_id: int, ctx: Ctx = Depends(member), db: Session = Depends(get_db)):
    t = _get_test(db, ctx, tid)
    r = db.get(DriftRun, run_id)
    if r is None or r.test_id != t.id or not r.response_text:
        raise HTTPException(404, "Run not found")
    t.baseline_text = r.response_text
    db.commit()
    return {"ok": True}


# =========================================================================== connect & credentials
@router.get("/llm/connect", tags=["llm"])
def connect_info(ctx: Ctx = Depends(require_access), db: Session = Depends(get_db)):
    base = get_settings().api_public_url.rstrip("/")
    creds = {p: bool(resolve_credential(db, ctx.workspace_id, p)) for p in PROVIDERS}
    return {"api_url": base,
            "base_urls": {"openai": f"{base}/gateway/openai/v1", "anthropic": f"{base}/gateway/anthropic",
                          "gemini": f"{base}/gateway/gemini"},
            "credentials": creds, "default_judge_models": DEFAULT_JUDGE_MODELS,
            "contracts": [c.slug for c in db.query(Contract).filter(Contract.workspace_id == ctx.workspace_id)]}


@router.post("/workspace/credentials/{cred_id}/test", tags=["workspace"])
async def test_credential(cred_id: int, ctx: Ctx = Depends(role("admin")), db: Session = Depends(get_db)):
    cred = db.get(ProviderCredential, cred_id)
    if cred is None or cred.workspace_id != ctx.workspace_id:
        raise HTTPException(404, "Credential not found")
    adapter = get_adapter(cred.provider)
    try:
        status, data, latency = await call_json(cred.provider, credential_key(db, cred), adapter.models_path(), method="GET")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "message": f"Could not reach {cred.provider}: {e}"}
    if status < 400:
        return {"ok": True, "message": f"Key works ({latency:.0f} ms)"}
    msg = data.get("error", {}).get("message") if isinstance(data, dict) and isinstance(data.get("error"), dict) else None
    return {"ok": False, "message": f"{cred.provider} returned HTTP {status}" + (f": {msg}" if msg else "")}

