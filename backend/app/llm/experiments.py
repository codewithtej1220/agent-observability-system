"""Experiments: run every item of a dataset against a model (and optionally a managed prompt version),
score each answer with the workspace's checks and a contract, and compare with the expected answer.

Each answer is a real (billed) call with the workspace's provider key, recorded as an LLM call with
source "experiment" so it never mixes with live traffic.
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional, Tuple

from ..db import SessionLocal
from ..orm import Workspace, utcnow
from ..orm_llm import Contract, DatasetItem, Experiment, ExperimentResult, LLMCall, Prompt
from ..pricing import estimate_cost
from .checks import CheckInput
from .drift import similarity
from .evaluator import evaluate
from .providers import estimate_tokens, get_adapter
from .upstream import call_json, credential_key, resolve_credential

log = logging.getLogger(__name__)
MAX_ITEMS = 200  # per experiment; each item is a billed provider call


def render(prompt: Optional[Prompt], item: DatasetItem) -> Tuple[str, str]:
    """(system, user) for one item: the prompt version's template with {{input}} filled, or the item as-is."""
    if prompt is None:
        return item.system_prompt, item.input
    user = prompt.template.replace("{{input}}", item.input) if prompt.template else item.input
    return prompt.system_prompt or item.system_prompt, user


async def run_experiment(experiment_id: int) -> None:
    db = SessionLocal()
    exp = None
    try:
        exp = db.get(Experiment, experiment_id)
        ws = db.get(Workspace, exp.workspace_id)
        contract = db.get(Contract, exp.contract_id) if exp.contract_id else None
        prompt = None
        if exp.prompt_name:
            prompt = (db.query(Prompt).filter(Prompt.workspace_id == ws.id, Prompt.name == exp.prompt_name,
                                              Prompt.version == exp.prompt_version).first())
        cred = resolve_credential(db, ws.id, exp.provider, cred_id=exp.credential_id)
        if cred is None:
            exp.status, exp.detail, exp.finished_at = "error", f"No {exp.provider} credential available", utcnow()
            db.commit()
            return
        adapter, key = get_adapter(exp.provider), credential_key(db, cred)
        items = (db.query(DatasetItem).filter(DatasetItem.dataset_id == exp.dataset_id)
                 .order_by(DatasetItem.id).limit(MAX_ITEMS).all())
        for item in items:
            db.add(await _run_item(db, ws, exp, contract, prompt, adapter, key, cred.id, item))
            db.commit()
        exp.summary, exp.status, exp.finished_at = summarize(db, exp.id), "done", utcnow()
        db.commit()
    except Exception as e:  # noqa: BLE001  (a failed experiment must not take the server down)
        log.exception("Experiment %s failed", experiment_id)
        db.rollback()
        if exp is not None:
            exp.status, exp.detail, exp.finished_at = "error", f"{type(e).__name__}: {e}"[:2000], utcnow()
            db.commit()
    finally:
        db.close()


async def _run_item(db, ws, exp, contract, prompt, adapter, key, cred_id, item) -> ExperimentResult:
    system, user = render(prompt, item)
    res = ExperimentResult(experiment_id=exp.id, item_id=item.id, status="error")
    path, body = adapter.simple_request(exp.model, system, user, max_tokens=1024)
    try:
        status, data, latency = await call_json(exp.provider, key, path, body)
    except Exception as e:  # noqa: BLE001
        res.detail = f"Request failed: {e}"[:2000]
        return res
    res.latency_ms = round(latency, 1)
    if status >= 400 or not isinstance(data, dict):
        res.detail = f"Provider returned HTTP {status}"
        return res
    c = adapter.parse_response(path, data)
    text = c.full_text
    ev = await evaluate(db, ws, contract, CheckInput(system, user, text, c.finish_reason))
    tin = c.input_tokens or estimate_tokens(system + user)
    tout = c.output_tokens or estimate_tokens(text)
    call = LLMCall(
        id=str(uuid.uuid4()), workspace_id=ws.id, provider=exp.provider, model=exp.model, endpoint="experiment",
        contract_id=exp.contract_id, credential_id=cred_id, source="experiment", tags=[f"experiment:{exp.name}"],
        prompt_name=exp.prompt_name, prompt_version=exp.prompt_version, latency_ms=res.latency_ms,
        system_prompt=system, last_user=user, n_messages=1, response_text=text[:20000], finish_reason=c.finish_reason,
        input_tokens=tin, output_tokens=tout, cost_usd=round(estimate_cost(exp.model, tin, tout), 6),
        eval_status="done", checks=[x.to_dict() for x in ev.checks], violations=len(ev.violations),
        adherence=ev.adherence, judge_score=ev.judge_score, relevance=ev.relevance, severity=ev.severity,
    )
    db.add(call)
    res.status, res.call_id, res.output, res.cost_usd = "ok", call.id, text[:20000], call.cost_usd
    res.violations = len(ev.violations)
    res.similarity = similarity(item.expected, text) if item.expected else None
    res.passed = not ev.violations and ev.severity != "critical"
    res.detail = "; ".join(f"{v.label} ({v.detail})" for v in ev.violations)[:2000]
    return res


def summarize(db, experiment_id: int) -> dict:
    rows = db.query(ExperimentResult).filter(ExperimentResult.experiment_id == experiment_id).all()
    ok = [r for r in rows if r.status == "ok"]
    sims = [r.similarity for r in ok if r.similarity is not None]
    return {
        "items": len(rows), "errors": len(rows) - len(ok), "passed": sum(r.passed for r in ok),
        "pass_rate": round(sum(r.passed for r in ok) / len(ok), 4) if ok else None,
        "avg_similarity": round(sum(sims) / len(sims), 4) if sims else None,
        "avg_latency_ms": round(sum(r.latency_ms for r in ok) / len(ok), 1) if ok else None,
        "cost_usd": round(sum(r.cost_usd for r in ok), 6),
    }
