"""In-process background loop: window alerts, scheduled drift tests, retention.

Runs inside the API process (one worker). For multiple API workers, run a
single dedicated instance with AOBS_BACKGROUND_JOBS=true and set it to false
on the others.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import timedelta

from ..db import SessionLocal
from ..orm import Workspace, utcnow
from ..orm_llm import LLMCall
from .alerts import evaluate_window_rules
from .drift import due_tests, run_test

log = logging.getLogger(__name__)
TICK_S = 30


def apply_retention(db) -> int:
    """Delete stored prompt/response content older than each workspace's retention period."""
    cleared = 0
    for ws in db.query(Workspace).all():
        cutoff = utcnow() - timedelta(days=int(ws.setting("retention_days") or 30))
        cleared += (db.query(LLMCall)
                    .filter(LLMCall.workspace_id == ws.id, LLMCall.created_at < cutoff, LLMCall.content_stored.is_(True))
                    .update({"system_prompt": "", "last_user": "", "response_text": "", "content_stored": False},
                            synchronize_session=False))
    db.commit()
    return cleared


async def tick(state: dict) -> None:
    db = SessionLocal()
    try:
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
