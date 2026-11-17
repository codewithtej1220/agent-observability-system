"""Stripe billing: Checkout for new subscriptions, the Customer Portal for
changes and cancellation, and webhooks to keep each workspace's plan in sync.

Stripe is optional. Configure AOBS_STRIPE_SECRET_KEY, AOBS_STRIPE_WEBHOOK_SECRET
and the recurring Price for Pro (AOBS_STRIPE_PRICE_PRO).
Webhook endpoint: {API}/api/billing/webhook, events: checkout.session.completed,
customer.subscription.created/updated/deleted, invoice.payment_failed.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import get_settings
from .llm.upstream import client
from .orm import BillingEvent, User, Workspace

log = logging.getLogger(__name__)
SIGNATURE_TOLERANCE_S = 300


def _flatten(data: Dict[str, Any], prefix: str = "") -> Dict[str, str]:
    """Stripe's form encoding: {"a": {"b": 1}} -> {"a[b]": "1"}, lists -> a[0]..."""
    out: Dict[str, str] = {}
    for k, v in data.items():
        key = f"{prefix}[{k}]" if prefix else k
        if isinstance(v, dict):
            out.update(_flatten(v, key))
        elif isinstance(v, list):
            for i, item in enumerate(v):
                if isinstance(item, dict):
                    out.update(_flatten(item, f"{key}[{i}]"))
                else:
                    out[f"{key}[{i}]"] = str(item)
        elif v is not None:
            out[key] = str(v).lower() if isinstance(v, bool) else str(v)
    return out


async def stripe_request(method: str, path: str, data: Optional[Dict] = None) -> Dict:
    s = get_settings()
    resp = await client().request(method, f"{s.stripe_api_base.rstrip('/')}/v1/{path}", data=_flatten(data or {}),
                                  headers={"Authorization": f"Bearer {s.stripe_secret_key}"}, timeout=20)
    body = resp.json() if resp.content else {}
    if resp.status_code >= 400:
        msg = (body.get("error") or {}).get("message", f"HTTP {resp.status_code}")
        log.warning("Stripe %s %s failed: %s", method, path, msg)
        raise HTTPException(502, f"Billing provider error: {msg}")
    return body


def _require_enabled() -> None:
    if not get_settings().stripe_enabled:
        raise HTTPException(503, "Online billing is not configured on this server. Ask the platform owner to change your plan.")


async def ensure_customer(db: Session, ws: Workspace, user: User) -> str:
    if ws.stripe_customer_id:
        return ws.stripe_customer_id
    cust = await stripe_request("POST", "customers", {
        "email": user.email, "name": ws.name, "metadata": {"workspace_id": ws.id}})
    ws.stripe_customer_id = cust["id"]
    db.commit()
    return cust["id"]


async def checkout_url(db: Session, ws: Workspace, user: User, plan_id: str) -> str:
    _require_enabled()
    s = get_settings()
    price = s.stripe_prices.get(plan_id)
    if not price:
        raise HTTPException(422, "Unknown plan")
    if ws.stripe_subscription_id:
        raise HTTPException(409, "This workspace already has a subscription. Use “Manage billing” to change plans.")
    customer = await ensure_customer(db, ws, user)
    base = s.public_url.rstrip("/")
    session = await stripe_request("POST", "checkout/sessions", {
        "mode": "subscription", "customer": customer, "client_reference_id": ws.id,
        "line_items": [{"price": price, "quantity": 1}],
        "subscription_data": {"metadata": {"workspace_id": ws.id, "plan": plan_id}},
        "metadata": {"workspace_id": ws.id, "plan": plan_id},
        "allow_promotion_codes": True,
        "success_url": f"{base}/settings?tab=billing&checkout=success",
        "cancel_url": f"{base}/settings?tab=billing&checkout=cancel",
    })
    return session["url"]


async def portal_url(db: Session, ws: Workspace) -> str:
    _require_enabled()
    if not ws.stripe_customer_id:
        raise HTTPException(409, "No billing account yet: choose a plan first.")
    session = await stripe_request("POST", "billing_portal/sessions", {
        "customer": ws.stripe_customer_id,
        "return_url": f"{get_settings().public_url.rstrip('/')}/settings?tab=billing"})
    return session["url"]


# --------------------------------------------------------------------------- webhooks
def verify_event(payload: bytes, sig_header: str, secret: str, now: Optional[float] = None) -> Dict:
    """Verify a Stripe-Signature header (HMAC-SHA256 over "{t}.{payload}") and parse the event."""
    if not secret:
        raise HTTPException(503, "Webhook secret not configured")
    parts: Dict[str, list] = {}
    for item in (sig_header or "").split(","):
        k, _, v = item.strip().partition("=")
        parts.setdefault(k, []).append(v)
    try:
        ts = int(parts["t"][0])
    except (KeyError, ValueError, IndexError):
        raise HTTPException(400, "Malformed signature header") from None
    if abs((now or time.time()) - ts) > SIGNATURE_TOLERANCE_S:
        raise HTTPException(400, "Signature timestamp outside tolerance")
    expected = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, v) for v in parts.get("v1", [])):
        raise HTTPException(400, "Invalid signature")
    return json.loads(payload)


def _plan_for_price(price_id: Optional[str]) -> Optional[str]:
    for plan, pid in get_settings().stripe_prices.items():
        if pid and pid == price_id:
            return plan
    return None


def _ts(v) -> Optional[datetime]:
    return datetime.fromtimestamp(int(v), tz=timezone.utc).replace(tzinfo=None) if v else None


def _find_workspace(db: Session, obj: Dict) -> Optional[Workspace]:
    meta = obj.get("metadata") or {}
    ws_id = meta.get("workspace_id") or obj.get("client_reference_id")
    if ws_id:
        ws = db.get(Workspace, int(ws_id))
        if ws:
            return ws
    customer = obj.get("customer")
    return db.query(Workspace).filter(Workspace.stripe_customer_id == customer).first() if customer else None


STATUS_MAP = {"active": "active", "trialing": "trialing", "past_due": "past_due", "unpaid": "canceled",
              "canceled": "canceled", "incomplete": "past_due", "incomplete_expired": "canceled", "paused": "canceled"}


def apply_event(db: Session, event: Dict) -> str:
    """Apply one webhook event to the matching workspace. Idempotent per event id."""
    etype, obj = event.get("type", ""), (event.get("data") or {}).get("object") or {}
    ws = _find_workspace(db, obj)
    try:
        db.add(BillingEvent(id=event["id"], type=etype, workspace_id=ws.id if ws else None))
        db.flush()
    except IntegrityError:
        db.rollback()
        return "duplicate"
    if ws is None:
        db.commit()
        return "ignored: no workspace"

    if etype == "checkout.session.completed":
        ws.stripe_customer_id = obj.get("customer") or ws.stripe_customer_id
        ws.stripe_subscription_id = obj.get("subscription") or ws.stripe_subscription_id
        plan = (obj.get("metadata") or {}).get("plan")
        if plan in get_settings().stripe_prices:
            ws.plan, ws.plan_status = plan, "active"
    elif etype in ("customer.subscription.created", "customer.subscription.updated"):
        items = (obj.get("items") or {}).get("data") or [{}]
        plan = _plan_for_price(((items[0].get("price") or {}).get("id"))) or (obj.get("metadata") or {}).get("plan")
        status = STATUS_MAP.get(obj.get("status"), "canceled")
        ws.stripe_subscription_id = obj.get("id")
        ws.stripe_customer_id = obj.get("customer") or ws.stripe_customer_id
        ws.current_period_end = _ts(obj.get("current_period_end") or items[0].get("current_period_end"))
        if status == "canceled":
            ws.plan, ws.plan_status, ws.stripe_subscription_id = "free", "active", None
        elif plan:
            ws.plan, ws.plan_status = plan, status
            if status == "trialing":
                ws.trial_ends_at = _ts(obj.get("trial_end"))
    elif etype == "customer.subscription.deleted":
        ws.plan, ws.plan_status, ws.stripe_subscription_id, ws.current_period_end = "free", "active", None, None
    elif etype == "invoice.payment_failed":
        if ws.plan != "free":
            ws.plan_status = "past_due"
    else:
        db.commit()
        return "ignored"
    db.commit()
    log.info("Billing: %s -> workspace %s now %s/%s", etype, ws.id, ws.plan, ws.plan_status)
    return "applied"
