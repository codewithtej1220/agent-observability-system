"""Plans, billing, the platform admin console, and the live event stream."""
from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from . import billing, plans
from .auth import Ctx, require_access, require_user, role
from .config import get_settings
from .db import get_db
from .orm import Membership, UsageCounter, User, Workspace
from .orm_llm import LLMCall
from .realtime import broker

router = APIRouter(prefix="/api")


# =========================================================================== plans & billing
@router.get("/plans", tags=["billing"])
def list_plans():
    """Public plan catalog (pricing page)."""
    return {"plans": [p.to_dict() for p in plans.PUBLIC_PLANS], "trial_days": plans.TRIAL_DAYS,
            "online_billing": get_settings().stripe_enabled}


@router.get("/billing", tags=["billing"])
def get_billing(ctx: Ctx = Depends(require_access), db: Session = Depends(get_db)):
    return {**plans.summary(db, ctx.workspace), "online_billing": get_settings().stripe_enabled,
            "trial_days": plans.TRIAL_DAYS, "can_manage": ctx.role == "admin"}


@router.post("/billing/trial", tags=["billing"])
def start_trial(ctx: Ctx = Depends(role("admin")), db: Session = Depends(get_db)):
    plans.start_trial(db, ctx.workspace)
    return plans.summary(db, ctx.workspace)


class CheckoutIn(BaseModel):
    plan: Literal["pro"]


@router.post("/billing/checkout", tags=["billing"])
async def checkout(body: CheckoutIn, ctx: Ctx = Depends(role("admin")), db: Session = Depends(get_db)):
    if ctx.user is None:
        raise HTTPException(403, "Sign in to subscribe")
    return {"url": await billing.checkout_url(db, ctx.workspace, ctx.user, body.plan)}


@router.post("/billing/portal", tags=["billing"])
async def portal(ctx: Ctx = Depends(role("admin")), db: Session = Depends(get_db)):
    return {"url": await billing.portal_url(db, ctx.workspace)}


@router.post("/billing/webhook", tags=["billing"], include_in_schema=False)
async def webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    event = billing.verify_event(payload, request.headers.get("stripe-signature", ""),
                                 get_settings().stripe_webhook_secret)
    return {"result": billing.apply_event(db, event)}


# =========================================================================== platform admin
def require_platform_admin(ctx: Ctx = Depends(require_user)) -> Ctx:
    if ctx.user.email.lower() not in get_settings().platform_admin_list:
        raise HTTPException(403, "Platform admins only")
    return ctx


@router.get("/admin/overview", tags=["admin"])
def admin_overview(ctx: Ctx = Depends(require_platform_admin), db: Session = Depends(get_db)):
    """Every workspace with its plan and this month's usage. Metadata only: no prompts or responses."""
    period = plans.period_key()
    usage: Dict[int, Dict[str, int]] = {}
    for row in db.query(UsageCounter).filter(UsageCounter.period == period):
        usage.setdefault(row.workspace_id, {})[row.metric] = row.count
    members = dict(db.query(Membership.workspace_id, func.count(Membership.id)).group_by(Membership.workspace_id).all())
    owners: Dict[int, str] = {}
    for m, u in (db.query(Membership, User).join(User, User.id == Membership.user_id)
                 .filter(Membership.role == "admin").order_by(Membership.id)):
        owners.setdefault(m.workspace_id, u.email)
    last_call = dict(db.query(LLMCall.workspace_id, func.max(LLMCall.created_at)).group_by(LLMCall.workspace_id).all())

    items, mrr, by_plan = [], 0, {}
    for ws in db.query(Workspace).order_by(Workspace.id):
        plan = plans.plan_of(ws)
        u = usage.get(ws.id, {})
        by_plan[plan.id] = by_plan.get(plan.id, 0) + 1
        if ws.plan_status == "active" and plan.price_month:
            mrr += plan.price_month
        items.append({
            "id": ws.id, "name": ws.name, "owner": owners.get(ws.id), "members": members.get(ws.id, 0),
            "plan": plan.id, "subscribed_plan": ws.plan, "status": ws.plan_status,
            "trial_ends_at": ws.trial_ends_at.isoformat() + "Z" if ws.trial_ends_at else None,
            "stripe": bool(ws.stripe_subscription_id),
            "created_at": ws.created_at.isoformat() + "Z" if ws.created_at else None,
            "last_call_at": last_call[ws.id].isoformat() + "Z" if last_call.get(ws.id) else None,
            "usage": {"llm_calls": u.get("llm_calls", 0), "llm_calls_unanalyzed": u.get("llm_calls_unanalyzed", 0),
                      "agent_runs": u.get("agent_runs", 0)},
            "limits": {"llm_calls": plan.llm_calls_month, "agent_runs": plan.agent_runs_month},
        })
    return {"period": period, "workspaces": items, "users": db.query(func.count(User.id)).scalar(),
            "mrr_usd": mrr, "by_plan": by_plan, "plans": [p.to_dict() for p in plans.PLANS.values()]}


class AdminWorkspaceIn(BaseModel):
    plan: Optional[Literal["free", "starter", "pro", "internal"]] = None
    plan_status: Optional[Literal["active", "trialing", "past_due", "canceled"]] = None


@router.patch("/admin/workspaces/{ws_id}", tags=["admin"])
def admin_update_workspace(ws_id: int, body: AdminWorkspaceIn, ctx: Ctx = Depends(require_platform_admin),
                           db: Session = Depends(get_db)):
    ws = db.get(Workspace, ws_id)
    if ws is None:
        raise HTTPException(404, "Workspace not found")
    if body.plan is not None:
        ws.plan = body.plan
        ws.plan_status = body.plan_status or "active"
        if ws.plan_status != "trialing":
            ws.trial_ends_at = None
    elif body.plan_status is not None:
        ws.plan_status = body.plan_status
    db.commit()
    return {"id": ws.id, "plan": plans.plan_of(ws).id, "status": ws.plan_status}


# =========================================================================== live updates
@router.get("/stream", tags=["realtime"])
async def stream(ctx: Ctx = Depends(require_access)):
    """Server-sent events for the current workspace: `call`, `alert`, `run`."""
    headers: Dict[str, Any] = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    return StreamingResponse(broker.stream(ctx.workspace_id), media_type="text/event-stream", headers=headers)
