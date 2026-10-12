"""Alert rules, alert events, and notification delivery.

Event rules fire on individual calls (PII in a response, prompt injection,
a blocked response, any critical result) or drift-test failures.
Window rules are evaluated every minute over a sliding window (violation
rate, error rate, p95 latency, judge score, adherence, cost), open one
alert while the condition holds, and resolve it automatically once it
clears. A cooldown prevents the same rule from paging repeatedly.

Every alert appears in the dashboard; Slack, webhook and email delivery are
optional per rule.
"""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import smtplib
import socket
from datetime import timedelta
from email.message import EmailMessage
from typing import Dict, List, Optional
from urllib.parse import urlparse

import numpy as np
from sqlalchemy.orm import Session

from ..config import get_settings
from ..orm import Workspace, utcnow
from ..orm_llm import EVENT_METRICS, WINDOW_METRICS, AlertEvent, AlertRule, LLMCall
from .upstream import client

log = logging.getLogger(__name__)
APP_SOURCES = ("gateway", "browser")  # real traffic (not drift tests)

METRIC_LABELS = {
    "violation_rate": "Violation rate", "error_rate": "Error rate", "p95_latency_ms": "p95 latency (ms)",
    "avg_judge_score": "Average judge score", "avg_adherence": "Average adherence", "cost_usd": "Cost (USD)",
    "event_pii": "Personal data in a response", "event_injection": "Prompt-injection attempt",
    "event_blocked": "Response blocked by contract", "event_critical": "Critical result on a call",
    "event_drift_failed": "Drift test failed",
}


# --------------------------------------------------------------------------- validation
def validate_webhook_url(url: str) -> str:
    """http(s) only; in production, no loopback/private/link-local targets (SSRF guard)."""
    u = urlparse(url)
    if u.scheme not in ("https", "http") or not u.hostname:
        raise ValueError("Webhook URL must be an http(s) URL")
    if get_settings().environment == "production":
        if u.scheme != "https":
            raise ValueError("Webhook URL must use https")
        try:
            infos = socket.getaddrinfo(u.hostname, None)
        except socket.gaierror as e:
            raise ValueError(f"Cannot resolve {u.hostname}") from e
        for info in infos:
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                raise ValueError("Webhook URL must not point to a private or local address")
    return url


def validate_rule(metric: str, comparison: str, channels: Dict) -> Dict:
    if metric not in WINDOW_METRICS + EVENT_METRICS:
        raise ValueError(f"Unknown metric '{metric}'")
    if comparison not in (">", "<"):
        raise ValueError("comparison must be > or <")
    out: Dict = {}
    for k in ("slack", "webhook"):
        if channels.get(k):
            out[k] = validate_webhook_url(channels[k].strip())
    emails = [e.strip() for e in (channels.get("email") or []) if e and "@" in e]
    if emails:
        out["email"] = emails[:10]
    return out


# --------------------------------------------------------------------------- delivery
def _link(ref_type: str, ref_id: str) -> str:
    base = get_settings().public_url.rstrip("/")
    return f"{base}/llm/calls/{ref_id}" if ref_type == "llm_call" else f"{base}/llm/alerts"


def _send_email(to: List[str], subject: str, body: str) -> None:
    s = get_settings()
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = s.smtp_from or s.smtp_user, ", ".join(to), subject
    msg.set_content(body)
    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as smtp:
        smtp.starttls()
        if s.smtp_user:
            smtp.login(s.smtp_user, s.smtp_password)
        smtp.send_message(msg)


async def deliver(rule: Optional[AlertRule], event: AlertEvent) -> List[Dict]:
    if rule is None:
        return []
    results = []
    ch = rule.channels or {}
    link = _link(event.ref_type, event.ref_id)
    text = f"[{event.severity.upper()}] {event.title}\n{event.message}\n{link}"
    payload = {"id": event.id, "title": event.title, "message": event.message, "severity": event.severity,
               "value": event.value, "rule": rule.name, "metric": rule.metric, "link": link,
               "created_at": event.created_at.isoformat() + "Z"}
    for kind, body in (("slack", {"text": text}), ("webhook", payload)):
        if ch.get(kind):
            try:
                r = await client().post(ch[kind], json=body, timeout=10)
                results.append({"channel": kind, "ok": r.status_code < 300, "status": r.status_code})
            except Exception as e:  # noqa: BLE001
                results.append({"channel": kind, "ok": False, "error": str(e)[:200]})
    if ch.get("email"):
        if not get_settings().smtp_host:
            results.append({"channel": "email", "ok": False, "error": "SMTP not configured (AOBS_SMTP_HOST)"})
        else:
            try:
                await asyncio.to_thread(_send_email, ch["email"], f"Alert: {event.title}", text)
                results.append({"channel": "email", "ok": True})
            except Exception as e:  # noqa: BLE001
                results.append({"channel": "email", "ok": False, "error": str(e)[:200]})
    return results


async def fire(db: Session, ws_id: int, rule: Optional[AlertRule], title: str, message: str, severity: str,
               value: Optional[float] = None, ref_type: str = "", ref_id: str = "") -> AlertEvent:
    ev = AlertEvent(workspace_id=ws_id, rule_id=rule.id if rule else None, title=title[:300], message=message,
                    severity=severity, value=value, ref_type=ref_type, ref_id=ref_id)
    db.add(ev)
    if rule is not None:
        rule.last_fired_at = utcnow()
    db.commit()
    ev.notified = await deliver(rule, ev)
    db.commit()
    return ev


def _in_cooldown(rule: AlertRule) -> bool:
    return rule.last_fired_at is not None and utcnow() - rule.last_fired_at < timedelta(minutes=rule.cooldown_minutes)


def _scope_match(rule: AlertRule, provider: str, model: str, contract_id: Optional[int]) -> bool:
    sc = rule.scope or {}
    return ((not sc.get("provider") or sc["provider"] == provider)
            and (not sc.get("model") or sc["model"] == model)
            and (not sc.get("contract_id") or sc["contract_id"] == contract_id))


# --------------------------------------------------------------------------- event rules
CALL_EVENTS = {
    "event_pii": lambda c: c.pii_flag,
    "event_injection": lambda c: c.injection_flag,
    "event_blocked": lambda c: c.enforcement_action == "blocked",
    "event_critical": lambda c: c.severity == "critical",
}


async def on_call_evaluated(db: Session, ws: Workspace, call: LLMCall) -> None:
    rules = db.query(AlertRule).filter(AlertRule.workspace_id == ws.id, AlertRule.enabled.is_(True),
                                       AlertRule.metric.in_(list(CALL_EVENTS))).all()
    for rule in rules:
        if not CALL_EVENTS[rule.metric](call) or not _scope_match(rule, call.provider, call.model, call.contract_id):
            continue
        if _in_cooldown(rule):
            continue
        failed = [c["label"] for c in call.checks if not c.get("passed", True) and not c.get("skipped")]
        await fire(db, ws.id, rule, f"{METRIC_LABELS[rule.metric]}: {call.provider}/{call.model}",
                   "Failed checks: " + (", ".join(failed) or "none"), "critical" if rule.metric != "event_injection" else "warning",
                   ref_type="llm_call", ref_id=call.id)


async def on_drift_failed(db: Session, ws_id: int, test, detail: str) -> None:
    rules = db.query(AlertRule).filter(AlertRule.workspace_id == ws_id, AlertRule.enabled.is_(True),
                                       AlertRule.metric == "event_drift_failed").all()
    if not rules:  # drift failures always show in-app, even without a rule
        await fire(db, ws_id, None, f"Drift test failed: {test.name}", detail, "warning", ref_type="drift_test",
                   ref_id=str(test.id))
        return
    for rule in rules:
        if _scope_match(rule, test.provider, test.model, test.contract_id) and not _in_cooldown(rule):
            await fire(db, ws_id, rule, f"Drift test failed: {test.name}", detail, "warning",
                       ref_type="drift_test", ref_id=str(test.id))


# --------------------------------------------------------------------------- window rules
def window_value(db: Session, rule: AlertRule) -> tuple:
    """(metric value or None, number of calls considered)."""
    since = utcnow() - timedelta(minutes=rule.window_minutes)
    q = db.query(LLMCall).filter(LLMCall.workspace_id == rule.workspace_id, LLMCall.created_at >= since,
                                 LLMCall.source.in_(APP_SOURCES))
    sc = rule.scope or {}
    if sc.get("provider"):
        q = q.filter(LLMCall.provider == sc["provider"])
    if sc.get("model"):
        q = q.filter(LLMCall.model == sc["model"])
    if sc.get("contract_id"):
        q = q.filter(LLMCall.contract_id == sc["contract_id"])
    calls = q.all()
    n = len(calls)
    m = rule.metric
    if m == "violation_rate":
        return (sum(c.violations > 0 for c in calls) / n if n else None), n
    if m == "error_rate":
        return (sum(c.status_code >= 400 and c.enforcement_action != "blocked" for c in calls) / n if n else None), n
    if m == "p95_latency_ms":
        return (float(np.percentile([c.latency_ms for c in calls], 95)) if n else None), n
    if m == "avg_judge_score":
        s = [c.judge_score for c in calls if c.judge_score is not None]
        return (float(np.mean(s)) if s else None), len(s)
    if m == "avg_adherence":
        s = [c.adherence for c in calls if c.adherence is not None]
        return (float(np.mean(s)) if s else None), len(s)
    if m == "cost_usd":
        return float(sum(c.cost_usd + c.judge_cost_usd for c in calls)), max(n, rule.min_calls)
    return None, 0


def _fmt(metric: str, v: float) -> str:
    if metric in ("violation_rate", "error_rate", "avg_adherence"):
        return f"{v:.1%}"
    if metric == "cost_usd":
        return f"${v:.2f}"
    if metric == "p95_latency_ms":
        return f"{v:.0f} ms"
    return f"{v:.2f}"


async def evaluate_window_rules(db: Session) -> int:
    fired = 0
    rules = db.query(AlertRule).filter(AlertRule.enabled.is_(True), AlertRule.metric.in_(list(WINDOW_METRICS))).all()
    for rule in rules:
        value, n = window_value(db, rule)
        breached = value is not None and n >= rule.min_calls and (
            value > rule.threshold if rule.comparison == ">" else value < rule.threshold)
        open_ev = (db.query(AlertEvent).filter(AlertEvent.rule_id == rule.id, AlertEvent.status != "resolved")
                   .order_by(AlertEvent.id.desc()).first())
        if breached and open_ev is None and not _in_cooldown(rule):
            await fire(db, rule.workspace_id, rule, f"{rule.name}: {METRIC_LABELS[rule.metric]} {_fmt(rule.metric, value)}",
                       f"{METRIC_LABELS[rule.metric]} is {_fmt(rule.metric, value)} over the last {rule.window_minutes} min "
                       f"({n} calls), threshold {rule.comparison} {_fmt(rule.metric, rule.threshold)}.",
                       "critical" if rule.metric in ("error_rate", "violation_rate") else "warning", value, "window", str(rule.id))
            fired += 1
        elif not breached and open_ev is not None:
            open_ev.status, open_ev.resolved_at = "resolved", utcnow()
            db.commit()
    return fired
