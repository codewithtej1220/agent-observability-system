"""Shared HTTP client for calls to LLM providers, and credential resolution."""
from __future__ import annotations

import time
from typing import Any, Dict, Optional, Tuple

import httpx
from sqlalchemy.orm import Session

from .. import crypto
from ..config import get_settings
from ..orm import ProviderCredential, utcnow
from .providers import get_adapter

_client: Optional[httpx.AsyncClient] = None
_transport: Optional[httpx.AsyncBaseTransport] = None


def set_transport(transport: Optional[httpx.AsyncBaseTransport]) -> None:
    """Tests inject httpx.MockTransport here to stand in for the real providers."""
    global _client, _transport
    _transport, _client = transport, None


def client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(get_settings().gateway_timeout_s, connect=10.0),
                                    transport=_transport, follow_redirects=False)
    return _client


async def close() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def resolve_credential(db: Session, workspace_id: int, provider: str,
                       name: Optional[str] = None, cred_id: Optional[int] = None) -> Optional[ProviderCredential]:
    q = db.query(ProviderCredential).filter(ProviderCredential.workspace_id == workspace_id,
                                            ProviderCredential.provider == provider)
    if cred_id is not None:
        return q.filter(ProviderCredential.id == cred_id).first()
    if name:
        return q.filter(ProviderCredential.name == name).first()
    return q.order_by(ProviderCredential.is_default.desc(), ProviderCredential.id).first()


def credential_key(db: Session, cred: ProviderCredential) -> str:
    now = utcnow()
    if cred.last_used_at is None or (now - cred.last_used_at).total_seconds() > 60:
        cred.last_used_at = now
        db.commit()
    return crypto.decrypt(cred.encrypted_key)


async def call_json(provider: str, key: str, path: str, body: Optional[Dict] = None,
                    method: str = "POST") -> Tuple[int, Any, float]:
    """One non-streaming request. Returns (status, parsed body or text, latency ms)."""
    adapter = get_adapter(provider)
    headers = {"content-type": "application/json", **adapter.auth_headers(key)}
    if provider == "anthropic":
        headers["anthropic-version"] = "2023-06-01"
    t0 = time.perf_counter()
    resp = await client().request(method, adapter.upstream_url(path), json=body, headers=headers)
    latency = (time.perf_counter() - t0) * 1000
    try:
        data = resp.json()
    except ValueError:
        data = resp.text
    return resp.status_code, data, latency
