"""In-process background loop: window alerts, scheduled drift tests, retention,
trial expiry.

Every API process runs the loop, but a lease row in the database lets only
one of them do the work at a time; if that process dies, another takes over
once the lease expires. Set AOBS_BACKGROUND_JOBS=false to opt a process out.
"""
from __future__ import annotations

import asyncio
import logging
import os
import socket
import time
from datetime import timedelta

from sqlalchemy.exc import IntegrityError

from .. import plans
from ..db import SessionLocal
from ..orm import JobLease, Workspace, utcnow
from ..orm_llm import LLMCall
from .alerts import evaluate_window_rules
from .drift import due_tests, run_test

log = logging.getLogger(__name__)
TICK_S = 30
LEASE_S = 90
HOLDER = f"{socket.gethostname()}:{os.getpid()}"


def acquire_lease(db, name: str = "background", holder: str = HOLDER, now=None) -> bool:
    """Take or renew the job lease; False while another live process holds it."""
    now = now or utcnow()
    lease = db.get(JobLease, name)
    if lease is None:
        try:
            db.add(JobLease(name=name, holder=holder, expires_at=now + timedelta(seconds=LEASE_S)))
            db.commit()
            return True
        except IntegrityError:
            db.rollback()
            return False
    if lease.holder != holder and lease.expires_at > now:
        return False
    # Conditional update so two processes cannot both take an expired lease.
    taken = (db.query(JobLease).filter(JobLease.name == name, JobLease.holder == lease.holder,
                                       JobLease.expires_at == lease.expires_at)
             .update({"holder": holder, "expires_at": now + timedelta(seconds=LEASE_S)}, synchronize_session=False))
    db.commit()
    return bool(taken)


def apply_retention(db) -> int:
    """Delete stored prompt/response content older than each workspace's retention period."""
    cleared = 0
    for ws in db.query(Workspace).all():
        cutoff = utcnow() - timedelta(days=plans.effective_retention(ws))
        cleared += (db.query(LLMCall)
                    .filter(LLMCall.workspace_id == ws.id, LLMCall.created_at < cutoff, LLMCall.content_stored.is_(True))
                    .update({"system_prompt": "", "last_user": "", "response_text": "", "content_stored": False},
                            synchronize_session=False))
    db.commit()
    return cleared


async def tick(state: dict) -> None:
    db = SessionLocal()
    try:
        if not acquire_lease(db):
            return
        if plans.expire_trials(db):
            log.info("Expired ended trials")
        await evaluate_window_rules(db)
        for test in list(due_tests(db)):
            try:
                await run_test(db, test)
            except Exception:  # noqa: BLE001
                log.exception("Drift test %s failed to run", test.id)
        if time.monotonic() - state.get("retention", 0) > 3600:
            n = apply_retention(db)
            state["retention"] = time.monotonic()
            if n:
                log.info("Retention: cleared content of %d LLM calls", n)
    finally:
        db.close()


async def run_forever() -> None:
    state: dict = {}
    while True:
        try:
            await tick(state)
        except Exception:  # noqa: BLE001
            log.exception("Background tick failed")
        await asyncio.sleep(TICK_S)
