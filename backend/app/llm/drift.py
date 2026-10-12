"""Provider drift tests.

Providers update models behind the same name. A drift test sends a fixed
prompt to a model on a schedule (temperature 0) and compares the answer with
a baseline: the first successful answer, unless you set one. A run fails when
similarity to the baseline drops below the threshold or the test's contract
rules are violated, and a failure raises an alert.

Similarity is lexical (word and word-pair overlap), so it detects changes in
content and format, not paraphrases with identical meaning. Set the
threshold accordingly, or attach a contract with judge rules for meaning.
"""
from __future__ import annotations

import logging
import uuid
from datetime import timedelta
from difflib import SequenceMatcher
from typing import Optional

from sqlalchemy.orm import Session

from ..orm import Workspace, utcnow
from ..orm_llm import Contract, DriftRun, DriftTest, LLMCall
from ..pricing import estimate_cost
from .alerts import on_drift_failed
from .checks import CheckInput, _terms
from .evaluator import evaluate
from .providers import estimate_tokens, get_adapter
from .upstream import call_json, credential_key, resolve_credential

log = logging.getLogger(__name__)


def similarity(a: str, b: str) -> float:
    ta, tb = _terms(a), _terms(b)
    if len(ta) >= 3 and len(tb) >= 3:
        dot = sum(ta[t] * tb[t] for t in ta.keys() & tb.keys())
        na = sum(v * v for v in ta.values()) ** 0.5
        nb = sum(v * v for v in tb.values()) ** 0.5
        return round(dot / (na * nb), 4) if na and nb else 0.0
    return round(SequenceMatcher(None, a.strip(), b.strip()).ratio(), 4)


async def run_test(db: Session, test: DriftTest) -> DriftRun:
    ws = db.get(Workspace, test.workspace_id)
    contract = db.get(Contract, test.contract_id) if test.contract_id else None
    cred = resolve_credential(db, test.workspace_id, test.provider, cred_id=test.credential_id)
    run = DriftRun(test_id=test.id, status="error")
    test.last_run_at = utcnow()
    if cred is None:
        run.detail = f"No {test.provider} credential available"
        return _save(db, test, run)

    adapter = get_adapter(test.provider)
    path, body = adapter.simple_request(test.model, test.system_prompt, test.prompt, max_tokens=1024)
    try:
        status, data, latency = await call_json(test.provider, credential_key(db, cred), path, body)
    except Exception as e:  # noqa: BLE001
        run.detail = f"Request failed: {e}"
        return _save(db, test, run)
    run.latency_ms = round(latency, 1)
    if status >= 400 or not isinstance(data, dict):
        run.detail = f"Provider returned HTTP {status}"
        return _save(db, test, run)

    c = adapter.parse_response(path, data)
    text = c.full_text
    run.response_text = text[:20000]
    run.output_tokens = c.output_tokens or estimate_tokens(text)
    ev = await evaluate(db, ws, contract, CheckInput(test.system_prompt, test.prompt, text, c.finish_reason))
    run.violations = len(ev.violations)
    _record_call(db, test, cred.id, c, text, latency, ev)

    if not test.baseline_text:
        test.baseline_text = text
        run.status, run.similarity, run.detail = "baseline", 1.0, "First answer saved as the baseline"
        return _save(db, test, run)

    run.similarity = similarity(test.baseline_text, text)
    problems = []
    if run.similarity < test.similarity_threshold:
        problems.append(f"similarity to baseline {run.similarity:.2f} < {test.similarity_threshold:.2f}")
    if ev.violations:
        problems.append("contract violations: " + "; ".join(f"{v.label} ({v.detail})" for v in ev.violations))
    run.status = "fail" if problems else "pass"
    run.detail = "; ".join(problems) or "Matches baseline"
    _save(db, test, run)
    if problems:
        await on_drift_failed(db, test.workspace_id, test,
                              f"{test.provider}/{test.model}: " + "; ".join(problems))
    return run


def _record_call(db, test, cred_id, c, text, latency, ev) -> None:
    tin = c.input_tokens or estimate_tokens(test.system_prompt + test.prompt)
    tout = c.output_tokens or estimate_tokens(text)
    db.add(LLMCall(
        id=str(uuid.uuid4()), workspace_id=test.workspace_id, provider=test.provider, model=test.model,
        endpoint="drift-test", contract_id=test.contract_id, credential_id=cred_id, source="drift_test",
        tags=[f"drift:{test.name}"], latency_ms=round(latency, 1), system_prompt=test.system_prompt,
        last_user=test.prompt, n_messages=1, response_text=text[:20000], finish_reason=c.finish_reason,
        input_tokens=tin, output_tokens=tout, cost_usd=round(estimate_cost(test.model, tin, tout), 6),
        eval_status="done", checks=[x.to_dict() for x in ev.checks], violations=len(ev.violations),
        adherence=ev.adherence, judge_score=ev.judge_score, relevance=ev.relevance, severity=ev.severity,
    ))


def _save(db: Session, test: DriftTest, run: DriftRun) -> DriftRun:
    test.last_status = run.status
    db.add(run)
    db.commit()
    return run


def due_tests(db: Session):
    now = utcnow()
    for t in db.query(DriftTest).filter(DriftTest.enabled.is_(True)).all():
        if t.last_run_at is None or now - t.last_run_at >= timedelta(minutes=t.interval_minutes):
            yield t


def latest_run(db: Session, test_id: int) -> Optional[DriftRun]:
    return db.query(DriftRun).filter(DriftRun.test_id == test_id).order_by(DriftRun.id.desc()).first()
