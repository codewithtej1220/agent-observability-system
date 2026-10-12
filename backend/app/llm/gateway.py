"""LLM gateway: an observing (and optionally enforcing) proxy for OpenAI, Anthropic and Gemini.

Point an official SDK at the gateway and use a workspace API key as its api_key:

    OpenAI     base_url = {API}/gateway/openai/v1
    Anthropic  base_url = {API}/gateway/anthropic
    Gemini     http_options.base_url = {API}/gateway/gemini

The provider key comes from the workspace's encrypted credentials (or, per
request, from an `X-Provider-Key` header). Optional headers, stripped before
forwarding:

    X-AOBS-Project      contract slug: which rules apply, and the enforcement mode
    X-AOBS-Session      conversation id, to group calls
    X-AOBS-User         your end-user's id
    X-AOBS-Tags         comma-separated labels
    X-AOBS-Credential   name of a stored credential other than the default

Modes (set on the contract):
    monitor  responses pass through untouched and are evaluated afterwards
             (no added latency).
    block    the response is evaluated before it is returned; critical rule
             violations return HTTP 422 instead of the response.
    repair   on violation, the model is asked to fix its answer (up to
             max_repairs times), then fallback models are tried, then blocked.
In block/repair modes streamed responses are buffered and released after the
check, so the client receives the whole stream at once.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from starlette.background import BackgroundTask

from ..auth import Ctx, api_key_ctx_or_401
from ..db import SessionLocal
from ..orm import Workspace
from ..orm_llm import Contract, LLMCall
from ..pricing import estimate_cost
from .checks import CheckInput, redact
from .evaluator import Evaluation, evaluate
from .providers import ADAPTERS, Adapter, Completion, Prompt, StreamAccumulator, estimate_tokens
from .upstream import client, credential_key, resolve_credential

log = logging.getLogger(__name__)
router = APIRouter(prefix="/gateway", tags=["gateway"])

RESPONSE_HEADER_PREFIXES = ("x-request-id", "request-id", "openai-", "anthropic-", "x-ratelimit", "retry-after")
REPAIR_INSTRUCTION = (
    "Your previous response did not meet these requirements:\n{violations}\n\n"
    "Rewrite your response so that it satisfies all of them. Reply with the corrected response only."
)


@dataclass
class CallMeta:
    call_id: str
    workspace_id: int
    provider: str
    path: str
    contract_id: Optional[int]
    credential_id: Optional[int]
    session_id: str = ""
    end_user: str = ""
    tags: List[str] = field(default_factory=list)


@dataclass
class Outcome:
    prompt: Prompt
    completion: Completion
    model: str
    status_code: int
    error: str = ""
    streamed: bool = False
    latency_ms: float = 0.0
    ttft_ms: Optional[float] = None
    evaluation: Optional[Evaluation] = None
    enforcement_action: str = "none"
    attempts: List[Dict] = field(default_factory=list)


def _error(adapter: Adapter, status: int, message: str, code: str = "aobs_gateway_error", details: Any = None):
    return JSONResponse(adapter.error_body(message, code, details), status_code=status)


def _response_headers(upstream_headers, call_id: str) -> Dict[str, str]:
    out = {k: v for k, v in upstream_headers.items() if k.lower().startswith(RESPONSE_HEADER_PREFIXES)}
    out["x-aobs-call-id"] = call_id
    return out


def _forward_headers(request: Request, adapter: Adapter, key: str) -> Dict[str, str]:
    allowed = adapter.passthrough_headers()
    h = {k: v for k, v in request.headers.items() if k.lower() in allowed}
    h.setdefault("content-type", "application/json")
    if adapter.name == "anthropic":
        h.setdefault("anthropic-version", "2023-06-01")
    h.update(adapter.auth_headers(key))
    return h


def _query(request: Request) -> Dict[str, str]:
    return {k: v for k, v in request.query_params.items() if k != "key"}


# --------------------------------------------------------------------------- persistence
async def finalize(meta: CallMeta, out: Outcome) -> None:
    """Evaluate (if not already done) and store the call, then fire event alerts."""
    from .alerts import on_call_evaluated

    db = SessionLocal()
    try:
        ws = db.get(Workspace, meta.workspace_id)
        contract = db.get(Contract, meta.contract_id) if meta.contract_id else None
        c, p = out.completion, out.prompt
        inp = CheckInput(p.system, p.last_user, c.full_text, c.finish_reason, c.tool_calls)
        ev = out.evaluation
        if ev is None or ev.judge_pending:
            blocked = out.enforcement_action == "blocked"  # score the upstream answer, not the 422 we returned
            ev = await evaluate(db, ws, contract, inp, status_code=200 if blocked else out.status_code,
                                error="" if blocked else out.error)
        tin = c.input_tokens if c.input_tokens is not None else estimate_tokens(p.all_text)
        tout = c.output_tokens if c.output_tokens is not None else estimate_tokens(c.full_text)
        store, red = bool(ws.setting("store_content")), bool(ws.setting("redact_pii"))

        def keep(text: str) -> str:
            return (redact(text) if red else text)[:100_000] if store else ""

        call = LLMCall(
            id=meta.call_id, workspace_id=meta.workspace_id, provider=meta.provider, model=out.model,
            endpoint=meta.path, contract_id=meta.contract_id, credential_id=meta.credential_id,
            session_id=meta.session_id, end_user=meta.end_user, tags=meta.tags,
            status_code=out.status_code, error=out.error[:2000], streamed=out.streamed,
            latency_ms=round(out.latency_ms, 1), ttft_ms=round(out.ttft_ms, 1) if out.ttft_ms else None,
            system_prompt=keep(p.system), last_user=keep(p.last_user), n_messages=len(p.messages),
            response_text=keep(c.full_text), content_stored=store, finish_reason=c.finish_reason,
            input_tokens=tin, output_tokens=tout,
            usage_estimated=c.input_tokens is None or c.output_tokens is None,
            cost_usd=round(estimate_cost(out.model, tin, tout), 6),
            eval_status="done", checks=[x.to_dict() for x in ev.checks], violations=len(ev.violations),
            adherence=ev.adherence, judge_score=ev.judge_score, judge_cost_usd=round(ev.judge_cost, 6),
            relevance=ev.relevance, pii_flag=ev.has("pii_output"), injection_flag=ev.has("prompt_injection"),
            severity=ev.severity, enforcement_action=out.enforcement_action, attempts=out.attempts,
        )
        db.add(call)
        db.commit()
        await on_call_evaluated(db, ws, call)
    except Exception:  # noqa: BLE001  (logging must never break the caller)
        log.exception("Failed to record LLM call %s", meta.call_id)
    finally:
        db.close()


# --------------------------------------------------------------------------- upstream calls
async def _send_buffered(adapter: Adapter, path: str, body: Dict, headers: Dict, query: Dict,
                         stream: bool) -> Tuple[int, bytes, Any, Completion, float, Optional[float]]:
    t0 = time.perf_counter()
    req = client().build_request("POST", adapter.upstream_url(path), content=json.dumps(body).encode(),
                                 headers=headers, params=query)
    resp = await client().send(req, stream=True)
    ttft = None
    try:
        if stream and resp.status_code < 400:
            acc = StreamAccumulator(adapter, path)
            async for chunk in resp.aiter_bytes():
                if ttft is None:
                    ttft = (time.perf_counter() - t0) * 1000
                acc.feed(chunk)
            raw, completion = bytes(acc.raw), acc.finish()
        else:
            raw = await resp.aread()
            completion = Completion()
            if resp.status_code < 400:
                try:
                    completion = adapter.parse_response(path, json.loads(raw))
                except (ValueError, TypeError, AttributeError):
                    pass
    finally:
        await resp.aclose()
    return resp.status_code, raw, resp.headers, completion, (time.perf_counter() - t0) * 1000, ttft


def _error_text(raw: bytes) -> str:
    try:
        d = json.loads(raw)
        err = d.get("error", d) if isinstance(d, dict) else d
        return err.get("message", json.dumps(err))[:500] if isinstance(err, dict) else str(err)[:500]
    except (ValueError, AttributeError):
        return raw[:500].decode("utf-8", "replace")


# --------------------------------------------------------------------------- route
@router.api_route("/{provider}/{path:path}", methods=["GET", "POST"])
async def proxy(provider: str, path: str, request: Request):
    adapter = ADAPTERS.get(provider)
    if adapter is None:
        raise HTTPException(404, f"Unknown provider '{provider}'. Use openai, anthropic or gemini.")

    db = SessionLocal()
    try:
        try:
            ctx: Ctx = api_key_ctx_or_401(request, db)
        except HTTPException as e:
            return _error(adapter, e.status_code, e.detail, "aobs_auth_error")
        ctx.require("member")
        cred = None
        key = request.headers.get("x-provider-key")
        if not key:
            cred = resolve_credential(db, ctx.workspace_id, provider, name=request.headers.get("x-aobs-credential"))
            if cred is None:
                return _error(adapter, 400, f"No {provider} API key is stored for this workspace. "
                                            f"Add one under Settings → Provider keys, or send X-Provider-Key.",
                              "aobs_missing_provider_key")
            key = credential_key(db, cred)
        headers = _forward_headers(request, adapter, key)
        query = _query(request)
        body_bytes = await request.body()

        if not adapter.is_generation(path, request.method):
            return await _passthrough(adapter, request.method, path, body_bytes, headers, query)

        try:
            body = json.loads(body_bytes or b"{}")
        except ValueError:
            return _error(adapter, 400, "Request body is not valid JSON", "invalid_request_error")
        prompt = adapter.parse_request(path, body)

        contract = None
        slug = request.headers.get("x-aobs-project")
        if slug:
            contract = db.query(Contract).filter(Contract.workspace_id == ctx.workspace_id, Contract.slug == slug,
                                                 Contract.active.is_(True)).first()
        meta = CallMeta(
            call_id=str(uuid.uuid4()), workspace_id=ctx.workspace_id, provider=provider, path=path,
            contract_id=contract.id if contract else None, credential_id=cred.id if cred else None,
            session_id=(request.headers.get("x-aobs-session") or "")[:200],
            end_user=(request.headers.get("x-aobs-user") or "")[:200],
            tags=[t.strip() for t in (request.headers.get("x-aobs-tags") or "").split(",") if t.strip()][:20],
        )
        if contract is None or contract.mode == "monitor":
            return await _monitor(adapter, path, body_bytes, headers, query, prompt, meta)
        ws = db.get(Workspace, ctx.workspace_id)
        return await _enforce(db, ws, contract, adapter, path, body, headers, query, prompt, meta)
    finally:
        db.close()


async def _passthrough(adapter, method, path, body_bytes, headers, query):
    req = client().build_request(method, adapter.upstream_url(path), content=body_bytes or None,
                                 headers=headers, params=query)
    resp = await client().send(req)
    return Response(resp.content, status_code=resp.status_code,
                    media_type=resp.headers.get("content-type"), headers=_response_headers(resp.headers, ""))


async def _monitor(adapter: Adapter, path: str, body_bytes: bytes, headers: Dict, query: Dict,
                   prompt: Prompt, meta: CallMeta):
    t0 = time.perf_counter()
    req = client().build_request("POST", adapter.upstream_url(path), content=body_bytes, headers=headers, params=query)
    resp = await client().send(req, stream=True)
    model = prompt.model or getattr(adapter, "model_of", lambda p: "")(path)
    out = Outcome(prompt=prompt, completion=Completion(), model=model, status_code=resp.status_code,
                  streamed=prompt.stream)
    resp_headers = _response_headers(resp.headers, meta.call_id)
    media = resp.headers.get("content-type", "application/json")

    if prompt.stream and resp.status_code < 400:
        acc = StreamAccumulator(adapter, path)

        async def relay():
            try:
                async for chunk in resp.aiter_bytes():
                    if out.ttft_ms is None:
                        out.ttft_ms = (time.perf_counter() - t0) * 1000
                    acc.feed(chunk)
                    yield chunk
            finally:
                await resp.aclose()
                out.completion = acc.finish()
                out.latency_ms = (time.perf_counter() - t0) * 1000

        return StreamingResponse(relay(), status_code=resp.status_code, media_type=media, headers=resp_headers,
                                 background=BackgroundTask(finalize, meta, out))

    raw = await resp.aread()
    await resp.aclose()
    out.latency_ms = (time.perf_counter() - t0) * 1000
    if resp.status_code < 400:
        try:
            out.completion = adapter.parse_response(path, json.loads(raw))
        except (ValueError, TypeError, AttributeError):
            pass
    else:
        out.error = _error_text(raw)
    return Response(raw, status_code=resp.status_code, media_type=media, headers=resp_headers,
                    background=BackgroundTask(finalize, meta, out))


async def _enforce(db, ws: Workspace, contract: Contract, adapter: Adapter, path: str, body: Dict,
                   headers: Dict, query: Dict, prompt: Prompt, meta: CallMeta):
    first_model = prompt.model or getattr(adapter, "model_of", lambda p: "")(path)
    models = [first_model] + [m for m in (contract.fallback_models or []) if m and m != first_model]
    attempts: List[Dict] = []
    total_latency = 0.0
    last: Optional[Tuple] = None
    last_ev: Optional[Evaluation] = None
    blocked_reason = ""

    for mi, model in enumerate(models):
        m_path, m_body = (path, body) if mi == 0 else adapter.with_model(path, body, model)
        cur = m_body
        tries = 1 + (max(0, contract.max_repairs) if contract.mode == "repair" else 0)
        for t in range(tries):
            status, raw, up_headers, completion, latency, ttft = await _send_buffered(
                adapter, m_path, cur, headers, query, prompt.stream)
            total_latency += latency
            if status >= 500 or status == 429:
                attempts.append({"model": model, "attempt": t, "status": status, "result": "upstream_error",
                                 "detail": _error_text(raw)})
                last = (status, raw, up_headers, completion, model, ttft)
                break  # try the next model
            if status >= 400:  # client error: return as-is, nothing to enforce
                attempts.append({"model": model, "attempt": t, "status": status, "result": "client_error"})
                out = Outcome(prompt, completion, model, status, _error_text(raw), prompt.stream, total_latency,
                              ttft, None, "none", attempts)
                return Response(raw, status_code=status, media_type=up_headers.get("content-type"),
                                headers=_response_headers(up_headers, meta.call_id),
                                background=BackgroundTask(finalize, meta, out))

            inp = CheckInput(prompt.system, prompt.last_user, completion.full_text, completion.finish_reason,
                             completion.tool_calls)
            ev = await evaluate(db, ws, contract, inp, use_judge=contract.judge_in_enforcement)
            crit = ev.critical_violations
            attempts.append({"model": model, "attempt": t, "status": status,
                             "result": "passed" if not crit else "violation",
                             "violations": [f"{c.label}: {c.detail}" for c in crit]})
            if not crit:
                action = "passed" if (mi == 0 and t == 0) else ("repaired" if mi == 0 else "fallback")
                out = Outcome(prompt, completion, model, status, "", prompt.stream, total_latency, ttft, ev,
                              action, attempts)
                hdrs = _response_headers(up_headers, meta.call_id)
                hdrs["x-aobs-enforcement"] = action
                return Response(raw, status_code=status, media_type=up_headers.get("content-type"), headers=hdrs,
                                background=BackgroundTask(finalize, meta, out))
            last = (status, raw, up_headers, completion, model, ttft)
            last_ev = ev
            blocked_reason = ev.violation_message()
            if contract.mode == "block":
                break
            if t + 1 < tries:
                cur = adapter.repair_request(m_path, cur, completion.full_text,
                                             REPAIR_INSTRUCTION.format(violations=ev.violation_message()))
        if contract.mode == "block" and blocked_reason:
            break

    if last is not None and not blocked_reason:
        # Every model failed upstream: surface the last provider error unchanged.
        status, raw, up_headers, completion, model, ttft = last
        out = Outcome(prompt, completion, model, status, _error_text(raw), prompt.stream, total_latency, ttft,
                      None, "none", attempts)
        return Response(raw, status_code=status, media_type=up_headers.get("content-type"),
                        headers=_response_headers(up_headers, meta.call_id),
                        background=BackgroundTask(finalize, meta, out))

    status, raw, up_headers, completion, model, ttft = last
    message = f"Response blocked by prompt contract '{contract.name}':\n{blocked_reason}"
    out = Outcome(prompt, completion, model, 422, "Blocked by contract", prompt.stream, total_latency, ttft, last_ev,
                  "blocked", attempts)
    resp = _error(adapter, 422, message, "aobs_policy_violation", {"contract": contract.slug, "attempts": attempts})
    resp.headers["x-aobs-call-id"] = meta.call_id
    resp.headers["x-aobs-enforcement"] = "blocked"
    resp.background = BackgroundTask(finalize, meta, out)
    return resp
