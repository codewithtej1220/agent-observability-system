"""Subscription plans, usage metering and plan limits.

Principles:
  * Monitoring must never break a customer's production traffic. When a
    workspace is over its monthly quota or rate limit, the LLM gateway still
    forwards requests; it just stops analyzing and storing them (fail-open).
    Endpoints whose only purpose is analysis (browser turns, agent ingest)
    return 402/429 instead, and the SDK and extension fail open on errors.
  * Configuration limits (members, contracts, alert rules, drift tests) are
    checked when something is created, with a clear upgrade message.
  * Feature gates (judge, enforcement, external alert channels) degrade
    gracefully: e.g. judge rules are reported as skipped, not failed.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import timedelta
from typing import Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .orm import Membership, UsageCounter, Workspace, utcnow

log = logging.getLogger(__name__)

UNLIMITED = None
TRIAL_DAYS = 14


@dataclass(frozen=True)
class Plan:
    id: str
    name: str
    price_month: Optional[int]          # USD; None = not sold publicly
    tagline: str
    llm_calls_month: Optional[int]
    agent_runs_month: Optional[int]
    seats: Optional[int]
    contracts: Optional[int]
    alert_rules: Optional[int]
    drift_tests: Optional[int]
    retention_days: int
    rate_per_min: int
    judge: bool
    enforcement: bool                   # block / repair / auto-correct modes
    channels: tuple = ("in_app",)
    public: bool = True
    highlights: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["channels"] = list(self.channels)
        return d


PLANS: Dict[str, Plan] = {
    "free": Plan(
        "free", "Free", 0, "Try it on a side project.",
        llm_calls_month=5_000, agent_runs_month=1_000, seats=2, contracts=2, alert_rules=3, drift_tests=1,
        retention_days=7, rate_per_min=120, judge=False, enforcement=False, channels=("in_app",),
        highlights=["5,000 tracked LLM calls / month", "Built-in safety checks", "Browser extension", "In-app alerts"],
    ),
    "pro": Plan(
        "pro", "Pro", 5, "Everything, for you or your team.",
        llm_calls_month=50_000, agent_runs_month=20_000, seats=5, contracts=10, alert_rules=20, drift_tests=5,
        retention_days=30, rate_per_min=600, judge=True, enforcement=True, channels=("in_app", "slack", "webhook", "email"),
        highlights=["50,000 tracked LLM calls / month", "LLM judge", "Block, repair and auto-correct",
                    "Slack, webhook and email alerts", "30-day retention", "14-day free trial"],
    ),
    # Retired: kept so workspaces that subscribed earlier keep their limits. Not offered.
    "starter": Plan(
        "starter", "Starter (legacy)", None, "Replaced by Pro.",
        llm_calls_month=50_000, agent_runs_month=20_000, seats=5, contracts=10, alert_rules=20, drift_tests=5,
        retention_days=30, rate_per_min=600, judge=True, enforcement=True, channels=("in_app", "slack", "webhook", "email"),
        public=False,
    ),
    # Internal plan for the platform owner's workspaces; assigned in the admin console only.
    "internal": Plan(
        "internal", "Internal", None, "Unlimited, for the platform owner.",
        llm_calls_month=UNLIMITED, agent_runs_month=UNLIMITED, seats=UNLIMITED, contracts=UNLIMITED,
        alert_rules=UNLIMITED, drift_tests=UNLIMITED, retention_days=365, rate_per_min=10_000, judge=True,
        enforcement=True, channels=("in_app", "slack", "webhook", "email"), public=False,
    ),
}
PUBLIC_PLANS = [p for p in PLANS.values() if p.public]
ACTIVE_STATUSES = ("active", "trialing", "past_due")  # past_due keeps access during payment retries


def plan_of(ws: Workspace) -> Plan:
    """The plan whose limits currently apply (expired or canceled subscriptions fall back to Free)."""
    plan = PLANS.get(ws.plan or "free", PLANS["free"])
    if plan.id == "free":
        return plan
    if ws.plan_status not in ACTIVE_STATUSES:
        return PLANS["free"]
    if ws.plan_status == "trialing" and ws.trial_ends_at and ws.trial_ends_at < utcnow():
        return PLANS["free"]
    return plan


def period_key(now=None) -> str:
    now = now or utcnow()
    return f"{now.year:04d}-{now.month:02d}"


# --------------------------------------------------------------------------- usage
def usage(db: Session, ws_id: int, metric: str, period: Optional[str] = None) -> int:
    row = db.get(UsageCounter, (ws_id, period or period_key(), metric))
    return row.count if row else 0


def increment(db: Session, ws_id: int, metric: str, by: int = 1) -> int:
    """Atomically add to this month's counter; returns the new value."""
    period = period_key()
    for _ in range(3):
        updated = (db.query(UsageCounter)
                   .filter(UsageCounter.workspace_id == ws_id, UsageCounter.period == period, UsageCounter.metric == metric)
                   .update({UsageCounter.count: UsageCounter.count + by}, synchronize_session=False))
        if updated:
            db.commit()
            return usage(db, ws_id, metric, period)
        try:
            db.add(UsageCounter(workspace_id=ws_id, period=period, metric=metric, count=by))
            db.commit()
            return by
        except IntegrityError:  # another request created it first: retry the update
            db.rollback()
    raise RuntimeError("Could not record usage")


METRIC_LIMIT = {"llm_calls": "llm_calls_month", "agent_runs": "agent_runs_month"}


def quota_left(db: Session, ws: Workspace, metric: str) -> Optional[int]:
    """Remaining monthly quota for a metered metric (None = unlimited)."""
    limit = getattr(plan_of(ws), METRIC_LIMIT[metric])
    if limit is None:
        return None
    return max(0, limit - usage(db, ws.id, metric))


def check_quota(db: Session, ws: Workspace, metric: str) -> None:
    """Raise 402 when the monthly quota is used up (for analysis-only endpoints)."""
    if quota_left(db, ws, metric) == 0:
        plan = plan_of(ws)
        label = {"llm_calls": "tracked LLM calls", "agent_runs": "agent runs"}[metric]
        raise HTTPException(402, f"Monthly limit of {getattr(plan, METRIC_LIMIT[metric]):,} {label} on the "
                                 f"{plan.name} plan reached. Upgrade in Settings → Plan & billing.")


def check_count(db: Session, ws: Workspace, what: str, current: int) -> None:
    """Raise 402 if creating one more `what` (seats, contracts, alert_rules, drift_tests) exceeds the plan."""
    plan = plan_of(ws)
    limit = getattr(plan, what)
    if limit is not None and current >= limit:
        label = {"seats": "members", "contracts": "contracts", "alert_rules": "alert rules", "drift_tests": "drift tests"}[what]
        raise HTTPException(402, f"The {plan.name} plan includes {limit} {label}. Upgrade in Settings → Plan & billing.")


def require_feature(ws: Workspace, feature: str) -> None:
    plan = plan_of(ws)
    if not getattr(plan, feature):
        name = {"judge": "The LLM judge", "enforcement": "Block, repair and auto-correct modes"}[feature]
        raise HTTPException(402, f"{name} is not included in the {plan.name} plan. Upgrade in Settings → Plan & billing.")


def check_channels(ws: Workspace, channels: Dict) -> None:
    plan = plan_of(ws)
    blocked = [c for c in ("slack", "webhook", "email") if channels.get(c) and c not in plan.channels]
    if blocked:
        raise HTTPException(402, f"{', '.join(blocked).capitalize()} alerts are not included in the {plan.name} plan. "
                                 "Upgrade in Settings → Plan & billing.")


def effective_retention(ws: Workspace) -> int:
    return min(int(ws.setting("retention_days") or 30), plan_of(ws).retention_days)


def seats_used(db: Session, ws_id: int) -> int:
    return db.query(func.count(Membership.id)).filter(Membership.workspace_id == ws_id).scalar() or 0


def start_trial(db: Session, ws: Workspace) -> None:
    if ws.trial_used:
        raise HTTPException(409, "This workspace has already used its free trial.")
    if plan_of(ws).id != "free":
        raise HTTPException(409, "Trials are for workspaces on the Free plan.")
    ws.plan, ws.plan_status, ws.trial_used = "pro", "trialing", True
    ws.trial_ends_at = utcnow() + timedelta(days=TRIAL_DAYS)
    db.commit()


def expire_trials(db: Session) -> int:
    """Move workspaces whose trial ended (and that did not subscribe) back to Free."""
    rows = (db.query(Workspace).filter(Workspace.plan_status == "trialing", Workspace.trial_ends_at < utcnow(),
                                       Workspace.stripe_subscription_id.is_(None)).all())
    for ws in rows:
        ws.plan, ws.plan_status = "free", "active"
    db.commit()
    return len(rows)


# --------------------------------------------------------------------------- rate limiting
class RateLimiter:
    """Per-workspace token bucket (in-process; use a shared store when running several API processes)."""

    def __init__(self):
        self._buckets: Dict[int, List[float]] = {}
        self._lock = threading.Lock()

    def allow(self, ws_id: int, per_min: int) -> bool:
        now = time.monotonic()
        with self._lock:
            tokens, last = self._buckets.get(ws_id, [float(per_min), now])
            tokens = min(float(per_min), tokens + (now - last) * per_min / 60.0)
            if tokens < 1:
                self._buckets[ws_id] = [tokens, now]
                return False
            self._buckets[ws_id] = [tokens - 1, now]
            return True


rate_limiter = RateLimiter()


def check_rate(ws: Workspace) -> None:
    if not rate_limiter.allow(ws.id, plan_of(ws).rate_per_min):
        raise HTTPException(429, f"Rate limit of {plan_of(ws).rate_per_min} requests per minute reached for this workspace.",
                            headers={"Retry-After": "10"})


def summary(db: Session, ws: Workspace) -> Dict:
    """Plan, limits and this month's usage, for the billing page and banners."""
    from .orm_llm import AlertRule, Contract, DriftTest  # local: avoid import cycle

    plan = plan_of(ws)
    counts = {
        "llm_calls": usage(db, ws.id, "llm_calls"),
        "agent_runs": usage(db, ws.id, "agent_runs"),
        "llm_calls_unanalyzed": usage(db, ws.id, "llm_calls_unanalyzed"),
        "seats": seats_used(db, ws.id),
        "contracts": db.query(func.count(Contract.id)).filter(Contract.workspace_id == ws.id).scalar(),
        "alert_rules": db.query(func.count(AlertRule.id)).filter(AlertRule.workspace_id == ws.id).scalar(),
        "drift_tests": db.query(func.count(DriftTest.id)).filter(DriftTest.workspace_id == ws.id).scalar(),
    }
    limits = {"llm_calls": plan.llm_calls_month, "agent_runs": plan.agent_runs_month, "seats": plan.seats,
              "contracts": plan.contracts, "alert_rules": plan.alert_rules, "drift_tests": plan.drift_tests}
    return {
        "plan": plan.to_dict(),
        "subscribed_plan": ws.plan or "free",
        "status": ws.plan_status or "active",
        "trial_ends_at": ws.trial_ends_at.isoformat() + "Z" if ws.trial_ends_at else None,
        "trial_available": not ws.trial_used and plan.id == "free",
        "current_period_end": ws.current_period_end.isoformat() + "Z" if ws.current_period_end else None,
        "has_billing_account": bool(ws.stripe_customer_id),
        "period": period_key(),
        "usage": counts,
        "limits": limits,
        "plans": [p.to_dict() for p in PUBLIC_PLANS],
    }
