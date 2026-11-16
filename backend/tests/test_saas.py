"""Subscriptions, quotas, billing webhooks, admin console, live updates and auto-correction."""
import asyncio
import hashlib
import hmac
import json
import time

import pytest

from conftest import set_plan
from test_gateway import CHAT, Gateway, GEMINI_KEY, OPENAI_KEY, ANTHROPIC_KEY  # noqa: F401
from mock_providers import MockProviders


@pytest.fixture
def free_gw(new_user):
    """Gateway on a Free-plan workspace."""
    from app.llm import upstream

    dash, _ = new_user()
    set_plan(dash, "free")  # the first signup adopts the (internal-plan) demo workspace
    key = dash.post("/api/workspace/api-keys", json={"name": "app"}).json()["key"]
    for provider, secret in (("openai", OPENAI_KEY), ("anthropic", ANTHROPIC_KEY), ("gemini", GEMINI_KEY)):
        dash.post("/api/workspace/credentials", json={"provider": provider, "api_key": secret})
    mock = MockProviders()
    upstream.set_transport(mock.transport())
    yield Gateway(dash, key, mock)
    upstream.set_transport(None)


@pytest.fixture
def pro_gw(free_gw):
    set_plan(free_gw.dash, "pro")
    return free_gw


def _ws_id(dash):
    return dash.get("/api/auth/me").json()["workspace"]["id"]


# --------------------------------------------------------------------------- plans
def test_public_plan_catalog(client):
    r = client.get("/api/plans")
    assert r.status_code == 200
    ids = [p["id"] for p in r.json()["plans"]]
    assert ids == ["free", "pro"]  # legacy and internal plans are never listed
    assert next(p for p in r.json()["plans"] if p["id"] == "pro")["price_month"] == 5


def test_new_workspace_starts_on_free_and_can_trial_once(new_user):
    dash, _ = new_user()
    set_plan(dash, "free")
    b = dash.get("/api/billing").json()
    assert b["plan"]["id"] == "free" and b["trial_available"] and b["usage"]["seats"] == 1
    r = dash.post("/api/billing/trial")
    assert r.status_code == 200 and r.json()["plan"]["id"] == "pro" and r.json()["status"] == "trialing"
    assert dash.post("/api/billing/trial").status_code == 409


def test_expired_trial_falls_back_to_free(new_user):
    from datetime import timedelta

    from app import plans
    from app.db import SessionLocal
    from app.orm import Workspace, utcnow

    dash, _ = new_user()
    set_plan(dash, "free")
    dash.post("/api/billing/trial")
    ws_id = _ws_id(dash)
    with SessionLocal() as db:
        ws = db.get(Workspace, ws_id)
        ws.trial_ends_at = utcnow() - timedelta(hours=1)
        db.commit()
        assert plans.plan_of(ws).id == "free"  # limits drop immediately
        assert plans.expire_trials(db) >= 1
        db.refresh(ws)
        assert ws.plan == "free" and ws.plan_status == "active"


def test_free_plan_limits_are_enforced_at_create_time(new_user):
    dash, _ = new_user()
    set_plan(dash, "free")
    r = dash.post("/api/llm/contracts", json={"name": "A", "slug": "a", "mode": "block", "rules": [{"type": "json_valid"}]})
    assert r.status_code == 402 and "not included" in r.json()["detail"]
    r = dash.post("/api/llm/contracts", json={"name": "A", "slug": "a", "rules": [
        {"type": "llm_judge", "params": {"instruction": "Be polite"}}]})
    assert r.status_code == 402
    for slug in ("a", "b"):
        assert dash.post("/api/llm/contracts", json={"name": slug, "slug": slug}).status_code == 200
    r = dash.post("/api/llm/contracts", json={"name": "c", "slug": "c"})
    assert r.status_code == 402 and "2 contracts" in r.json()["detail"]

    rule = {"name": "PII", "metric": "event_pii", "channels": {"slack": "https://hooks.slack.com/services/x"}}
    assert dash.post("/api/llm/alert-rules", json=rule).status_code == 402
    assert dash.post("/api/llm/alert-rules", json={**rule, "channels": {}}).status_code == 200


def test_downgrade_keeps_existing_contract_editable(new_user):
    dash, _ = new_user()
    set_plan(dash, "pro")
    c = dash.post("/api/llm/contracts", json={"name": "A", "slug": "a", "mode": "block",
                                              "rules": [{"type": "json_valid"}]}).json()
    set_plan(dash, "free")
    r = dash.patch(f"/api/llm/contracts/{c['id']}", json={"name": "A2", "slug": "a", "mode": "block",
                                                          "rules": [{"type": "json_valid"}]})
    assert r.status_code == 200 and r.json()["name"] == "A2"


def test_free_plan_gateway_runs_block_contract_as_monitor(free_gw):
    set_plan(free_gw.dash, "pro")
    free_gw.contract(mode="block", rules=[{"type": "json_valid"}])
    set_plan(free_gw.dash, "free")
    r = free_gw.openai(CHAT, **{"X-AOBS-Project": "support"})
    assert r.status_code == 200 and "x-aobs-enforcement" not in r.headers
    assert free_gw.last_call()["violations"] == 1  # still detected, just not enforced


# --------------------------------------------------------------------------- quota and rate (fail-open)
def test_over_quota_gateway_forwards_without_analysis(free_gw):
    from app import plans
    from app.db import SessionLocal

    ws_id = _ws_id(free_gw.dash)
    with SessionLocal() as db:
        plans.increment(db, ws_id, "llm_calls", plans.PLANS["free"].llm_calls_month)
    before = free_gw.dash.get("/api/llm/calls").json()["total"]
    r = free_gw.openai(CHAT)
    assert r.status_code == 200 and r.json()["choices"][0]["message"]["content"].startswith("Paris")
    assert r.headers["x-aobs-analysis"] == "skipped-quota"
    assert free_gw.dash.get("/api/llm/calls").json()["total"] == before  # not stored
    b = free_gw.dash.get("/api/billing").json()
    assert b["usage"]["llm_calls_unanalyzed"] == 1
    alerts = free_gw.dash.get("/api/llm/alerts").json()
    assert any("limit reached" in a["title"] for a in alerts)
    free_gw.openai(CHAT)
    alerts = free_gw.dash.get("/api/llm/alerts").json()
    assert sum("limit reached" in a["title"] for a in alerts) == 1  # one notice per month


def test_over_quota_browser_turn_is_refused(free_gw):
    from app import plans
    from app.db import SessionLocal

    with SessionLocal() as db:
        plans.increment(db, _ws_id(free_gw.dash), "llm_calls", plans.PLANS["free"].llm_calls_month)
    r = free_gw.dash.post("/api/llm/ingest/browser-turn", json={"app": "gemini-web", "turn_id": "t1", "response": "hi"})
    assert r.status_code == 402


def test_rate_limiter_token_bucket():
    from app.plans import RateLimiter

    rl = RateLimiter()
    assert all(rl.allow(999, 5) for _ in range(5))
    assert not rl.allow(999, 5)


def test_usage_counts_each_analyzed_call(free_gw):
    free_gw.openai(CHAT)
    free_gw.openai(CHAT)
    assert free_gw.dash.get("/api/billing").json()["usage"]["llm_calls"] == 2


# --------------------------------------------------------------------------- billing webhooks
def _signed(payload: dict, secret: str, ts=None):
    body = json.dumps(payload).encode()
    ts = ts or int(time.time())
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return body, f"t={ts},v1={sig}"


@pytest.fixture
def stripe_settings():
    from app.config import get_settings

    s = get_settings()
    old = (s.stripe_webhook_secret, s.stripe_price_starter, s.stripe_price_pro)
    s.stripe_webhook_secret, s.stripe_price_starter, s.stripe_price_pro = "whsec_test", "price_starter", "price_pro"
    yield s
    s.stripe_webhook_secret, s.stripe_price_starter, s.stripe_price_pro = old


def test_webhook_signature_and_idempotency(client, new_user, stripe_settings):
    dash, _ = new_user()
    ws_id = _ws_id(dash)
    event = {"id": "evt_1", "type": "customer.subscription.updated", "data": {"object": {
        "id": "sub_1", "customer": "cus_1", "status": "active", "metadata": {"workspace_id": str(ws_id)},
        "items": {"data": [{"price": {"id": "price_pro"}}]}, "current_period_end": int(time.time()) + 86400 * 30}}}
    body, sig = _signed(event, "wrong")
    assert client.post("/api/billing/webhook", content=body, headers={"stripe-signature": sig}).status_code == 400
    body, sig = _signed(event, "whsec_test", ts=int(time.time()) - 3600)
    assert client.post("/api/billing/webhook", content=body, headers={"stripe-signature": sig}).status_code == 400

    body, sig = _signed(event, "whsec_test")
    r = client.post("/api/billing/webhook", content=body, headers={"stripe-signature": sig})
    assert r.status_code == 200 and r.json()["result"] == "applied"
    assert dash.get("/api/billing").json()["plan"]["id"] == "pro"
    r = client.post("/api/billing/webhook", content=body, headers={"stripe-signature": sig})
    assert r.json()["result"] == "duplicate"

    cancel = {"id": "evt_2", "type": "customer.subscription.deleted", "data": {"object": {
        "id": "sub_1", "customer": "cus_1", "status": "canceled"}}}
    body, sig = _signed(cancel, "whsec_test")
    assert client.post("/api/billing/webhook", content=body, headers={"stripe-signature": sig}).json()["result"] == "applied"
    assert dash.get("/api/billing").json()["plan"]["id"] == "free"


def test_checkout_without_stripe_explains(new_user):
    dash, _ = new_user()
    r = dash.post("/api/billing/checkout", json={"plan": "pro"})
    assert r.status_code == 503 and "not configured" in r.json()["detail"]


# --------------------------------------------------------------------------- admin console
def test_admin_console_requires_platform_admin(new_user):
    from app.config import get_settings

    dash, email = new_user()
    assert dash.get("/api/admin/overview").status_code == 403
    assert dash.get("/api/auth/me").json()["is_platform_admin"] is False
    s = get_settings()
    old = s.platform_admins
    s.platform_admins = email
    try:
        assert dash.get("/api/auth/me").json()["is_platform_admin"] is True
        ov = dash.get("/api/admin/overview").json()
        mine = next(w for w in ov["workspaces"] if w["owner"] == email)
        assert "response_text" not in json.dumps(ov)  # metadata only
        r = dash.patch(f"/api/admin/workspaces/{mine['id']}", json={"plan": "internal"})
        assert r.status_code == 200 and r.json()["plan"] == "internal"
        assert dash.get("/api/billing").json()["plan"]["id"] == "internal"
    finally:
        s.platform_admins = old


# --------------------------------------------------------------------------- live updates
def test_broker_delivers_to_workspace_subscribers_only():
    from app.realtime import Broker

    async def run():
        b = Broker()
        b.bind(asyncio.get_running_loop())
        mine, other = b.stream(1), b.stream(2)
        assert (await mine.__anext__()).startswith(b": connected")
        await other.__anext__()
        b.publish(1, "call", {"id": "abc"})
        b.publish(3, "call", {"id": "nobody"})
        msg = await asyncio.wait_for(mine.__anext__(), 1)
        assert msg == b'event: call\ndata: {"id": "abc"}\n\n'
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(other.__anext__(), 0.1)
        await mine.aclose()
        assert b.subscribers(1) == 0

    asyncio.run(run())


def test_stream_requires_auth(new_user):
    from fastapi.testclient import TestClient

    from app.main import app

    assert TestClient(app).get("/api/stream").status_code == 401


# --------------------------------------------------------------------------- auto-correction
PII_TEXT = "Contact our agent at jane.doe@example.com or 555-123-4567."


def test_autocorrect_redacts_pii_nonstream(pro_gw):
    pro_gw.contract(mode="block", rules=[{"type": "no_pii"}])
    pro_gw.mock.texts = [PII_TEXT]
    r = pro_gw.openai(CHAT, **{"X-AOBS-Project": "support"})
    assert r.status_code == 200 and r.headers["x-aobs-enforcement"] == "corrected"
    content = r.json()["choices"][0]["message"]["content"]
    assert "jane.doe@example.com" not in content and "555-123-4567" not in content
    assert len(pro_gw.mock.requests) == 1  # fixed without another model call
    call = pro_gw.last_call()
    assert call["enforcement_action"] == "corrected"
    assert call["attempts"][-1]["fixes"] == ["Masked personal data"]


def test_autocorrect_can_be_disabled(pro_gw):
    pro_gw.contract(mode="block", rules=[{"type": "no_pii"}], auto_redact=False)
    pro_gw.mock.texts = [PII_TEXT]
    assert pro_gw.openai(CHAT, **{"X-AOBS-Project": "support"}).status_code == 422


def test_autocorrect_extracts_json(pro_gw):
    pro_gw.contract(mode="block", rules=[{"type": "json_valid"}])
    pro_gw.mock.texts = ['Sure! Here it is:\n```json\n{"answer": "Paris"}\n```']
    r = pro_gw.openai(CHAT, **{"X-AOBS-Project": "support"})
    assert r.status_code == 200 and r.headers["x-aobs-enforcement"] == "corrected"
    assert json.loads(r.json()["choices"][0]["message"]["content"]) == {"answer": "Paris"}


def _sse_text(raw: str, provider: str) -> str:
    out = []
    for line in raw.splitlines():
        if not line.startswith("data: ") or line == "data: [DONE]":
            continue
        d = json.loads(line[6:])
        if provider == "openai":
            out += [c["delta"].get("content") or "" for c in d["choices"]]
        elif provider == "anthropic" and d["type"] == "content_block_delta":
            out.append(d["delta"]["text"])
        elif provider == "gemini":
            out += [p.get("text", "") for p in d["candidates"][0]["content"]["parts"]]
    return "".join(out)


def test_autocorrect_streams_for_every_provider(pro_gw):
    pro_gw.contract(mode="block", rules=[{"type": "no_pii"}])
    hdr = {"X-AOBS-Project": "support"}

    pro_gw.mock.texts = [PII_TEXT]
    r = pro_gw.openai({**CHAT, "stream": True}, **hdr)
    assert r.headers["x-aobs-enforcement"] == "corrected"
    text = _sse_text(r.text, "openai")
    assert "jane.doe" not in text and text.startswith("Contact our agent") and r.text.endswith("data: [DONE]\n\n")

    pro_gw.mock.texts = [PII_TEXT]
    r = pro_gw.anthropic({"model": "claude-x", "max_tokens": 100, "stream": True,
                          "messages": [{"role": "user", "content": "Who do I contact?"}]}, **hdr)
    assert r.headers["x-aobs-enforcement"] == "corrected"
    assert "jane.doe" not in _sse_text(r.text, "anthropic") and "event: message_stop" in r.text

    pro_gw.mock.texts = [PII_TEXT]
    r = pro_gw.gemini("gemini-2.0-flash", {"contents": [{"role": "user", "parts": [{"text": "Who?"}]}]}, stream=True, **hdr)
    assert r.headers["x-aobs-enforcement"] == "corrected"
    text = _sse_text(r.text, "gemini")
    assert "jane.doe" not in text and text.startswith("Contact our agent")


# --------------------------------------------------------------------------- feedback / check quality
def test_feedback_measures_check_precision(pro_gw):
    pro_gw.contract(rules=[{"type": "json_valid"}])
    pro_gw.openai(CHAT, **{"X-AOBS-Project": "support"})
    call = pro_gw.last_call()
    r = pro_gw.dash.post(f"/api/llm/calls/{call['id']}/feedback", json={"verdict": "false_positive", "note": "plain text ok"})
    assert r.status_code == 200
    pro_gw.dash.post(f"/api/llm/calls/{call['id']}/feedback", json={"verdict": "correct"})  # changes, not duplicates
    detail = pro_gw.dash.get(f"/api/llm/calls/{call['id']}").json()
    assert [f["verdict"] for f in detail["feedback"]] == ["correct"]
    q = pro_gw.dash.get("/api/llm/check-quality").json()
    item = next(i for i in q["items"] if i["type"] == "json_valid")
    assert item["confirmed"] == 1 and item["precision"] == 1.0


# --------------------------------------------------------------------------- agent corrections
def test_correction_prompt_for_continuing_actions():
    from ml.corrections import build_correction

    sig = [{"failure_type": "loop", "detector": "repeat", "severity": 0.9,
            "message": "search_docs called 4 times with identical arguments", "evidence_steps": [5, 6, 7, 8]}]  # 0-based in the API
    c = build_correction("loop", sig, "reflect")
    assert c["action"] == "reflect" and "steps 6–9" in c["prompt"] and "Do not repeat" in c["prompt"]
    assert build_correction("loop", sig, "terminate") is None
    h = build_correction("hallucinated_tool", [], "retry_step", tools=["search", "lookup"])
    assert "(search, lookup)" in h["prompt"] and h["prompt"].endswith("Redo your last step with these corrections.")


def test_ingest_meters_agent_runs(new_user, make_run):
    from app import plans
    from app.db import SessionLocal
    from scripts.bootstrap import run_to_payload

    dash, _ = new_user()
    set_plan(dash, "free")
    payload = run_to_payload(make_run("loop", seed=3), None).model_dump(mode="json")
    payload2 = run_to_payload(make_run("loop", seed=4), None).model_dump(mode="json")
    r = dash.post("/api/ingest/runs", json=payload)
    assert r.status_code == 200, r.text
    assert "correction" in r.json()
    assert dash.get("/api/billing").json()["usage"]["agent_runs"] == 1
    with SessionLocal() as db:
        plans.increment(db, _ws_id(dash), "agent_runs", plans.PLANS["free"].agent_runs_month)
    assert dash.post("/api/ingest/runs", json=payload2).status_code == 402


def test_health_ready_and_security_headers(client):
    r = client.get("/health/ready")
    assert r.status_code == 200 and r.json()["database"] == "ok"
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-request-id"]


# --------------------------------------------------------------------------- per-model baseline
def test_model_baseline_flags_unusual_answers(pro_gw):
    from app.db import SessionLocal
    from app.llm import baseline
    from app.orm_llm import LLMCall

    ws_id = _ws_id(pro_gw.dash)
    with SessionLocal() as db:
        for i in range(60):
            db.add(LLMCall(id=f"base-{ws_id}-{i}", workspace_id=ws_id, provider="openai", model="gpt-base",
                           endpoint="v1/chat/completions", status_code=200, latency_ms=800 + (i % 7) * 20,
                           output_tokens=100 + (i % 9) * 5, relevance=0.6 + (i % 5) * 0.02))
        db.commit()
        baseline._cache.clear()
        assert baseline.check(db, ws_id, "openai", "gpt-base",
                              {"output_tokens": 110, "latency_ms": 820, "relevance": 0.62}) is None
        r = baseline.check(db, ws_id, "openai", "gpt-base", {"output_tokens": 4, "latency_ms": 9000, "relevance": 0.6})
        assert r is not None and r.severity == "info" and "shorter" in r.detail and "slower" in r.detail
        assert baseline.check(db, ws_id, "openai", "unknown-model", {"output_tokens": 4}) is None  # no history yet
