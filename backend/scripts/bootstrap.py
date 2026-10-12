"""Bootstrap a working system from scratch.

    python -m scripts.bootstrap            (from backend/)
    python -m scripts.bootstrap --reset    wipe database and artifacts first

Steps:
  1. Register the simulated agents and their tool sets.
  2. Train model v1 on simulated reference data; evaluate on a held-out set,
     including the leave-one-failure-type-out robustness study.
  3. Warm-start the intervention policy offline.
  4. Replay N days of agent traffic through the real ingestion path, with a
     simulated incident, and simulated reviewer feedback day by day (so the
     policy keeps learning online, as it would in production).
  5. Seed simulated LLM gateway traffic (demo contracts, alerts, drift test).
  6. Retrain (v2) with the human labels collected in step 4.

Simulated traffic carries its ground-truth label in `source_label`; the
models never see it. Point real agents at the API (see sdk/) to replace it.
"""
from __future__ import annotations

import argparse
import logging
import random
import shutil
import sys
import time
from datetime import timedelta
from pathlib import Path
from typing import List

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.db import Base, SessionLocal, engine, init_db  # noqa: E402
from app.auth import DEMO_WORKSPACE_NAME, demo_workspace  # noqa: E402
from app.orm import DEFAULT_WORKSPACE_SETTINGS, Agent, RunRecord, Workspace, utcnow  # noqa: E402
from app.schemas import FeedbackIn, RunIn, StepIn  # noqa: E402
from app.services import ingest, training  # noqa: E402
from app.services.registry import registry  # noqa: E402
from ml.schema import Run  # noqa: E402
from ml.simulator import AGENT_BY_ID, AGENTS, generate_run, simulate_outcome  # noqa: E402

log = logging.getLogger("bootstrap")


def run_to_payload(run: Run, started_at) -> RunIn:
    return RunIn(
        run_id=run.run_id, agent_id=run.agent_id, task=run.task, model=run.model,
        registered_tools=run.registered_tools, started_at=started_at,
        source_label=run.source_label, failure_onset=run.failure_onset,
        steps=[StepIn(type=s.type, tool_name=s.tool_name, arguments=s.arguments, output=s.output, status=s.status,
                      latency_ms=s.latency_ms, input_tokens=s.input_tokens, output_tokens=s.output_tokens)
               for s in run.steps],
    )


def ensure_demo_workspace(db) -> int:
    ws = demo_workspace(db)
    if ws is None:
        ws = Workspace(name=DEMO_WORKSPACE_NAME, settings=dict(DEFAULT_WORKSPACE_SETTINGS))
        db.add(ws)
        db.commit()
    return ws.id


def register_agents(db, ws_id: int) -> None:
    for a in AGENTS:
        row = db.get(Agent, (ws_id, a.agent_id)) or Agent(workspace_id=ws_id, id=a.agent_id)
        row.name, row.description, row.model, row.framework = a.name, a.description, a.model, a.framework
        row.registered_tools = a.tool_names
        db.add(row)
    db.commit()


def hourly_volume(hour: int, base: float) -> int:
    """Business-hours traffic shape."""
    shape = 0.35 + 0.65 * np.exp(-((hour - 14) ** 2) / 18.0)
    return int(np.random.poisson(base * shape))


def seed_history(db, ws_id: int, days: int, runs_per_hour: float, feedback_share: float, seed: int) -> None:
    rng = random.Random(seed)
    np.random.seed(seed)
    outcome_rng = np.random.default_rng(seed)
    now = utcnow().replace(minute=0, second=0, microsecond=0)
    start = now - timedelta(days=days)
    incident_start = now - timedelta(days=2, hours=10)
    incident_end = incident_start + timedelta(hours=7)
    research = AGENT_BY_ID["research-agent"]
    total_runs = total_feedback = 0

    for day in range(days + 1):
        day_payloads: List[RunIn] = []
        for hour in range(24):
            t_hour = start + timedelta(days=day, hours=hour)
            if t_hour > now:
                break
            for _ in range(hourly_volume(t_hour.hour, runs_per_hour)):
                t = t_hour + timedelta(seconds=rng.uniform(0, 3599))
                if t > utcnow():
                    continue
                if incident_start <= t < incident_end and rng.random() < 0.35:
                    # Incident: a prompt change made the research agent loop.
                    run = generate_run(rng, agent=research, label=rng.choice(["loop", "loop", "token_waste"]))
                else:
                    run = generate_run(rng)
                day_payloads.append(run_to_payload(run, t))
        if not day_payloads:
            continue
        day_payloads.sort(key=lambda p: p.started_at)
        for i in range(0, len(day_payloads), 250):
            ingest.ingest_runs(db, ws_id, day_payloads[i:i + 250])
        total_runs += len(day_payloads)

        # Reviewers label a share of that day's flagged runs (and a few unflagged ones).
        ids = [p.run_id for p in day_payloads]
        recs = db.query(RunRecord).filter(RunRecord.id.in_(ids)).all()
        for rec in recs:
            flagged = rec.severity != "healthy"
            if rng.random() > (feedback_share if flagged else 0.02):
                continue
            if rec.started_at > now - timedelta(hours=24) and rng.random() < 0.7:
                continue  # leave recent work in the review queue
            label = rec.source_label or "healthy"
            action = rec.recommended_action
            resolved = simulate_outcome(outcome_rng, label, action)
            ingest.record_feedback(db, ws_id, rec.id, FeedbackIn(label=label, action_taken=action, resolved=resolved,
                                                          reviewer="simulated-reviewer"))
            total_feedback += 1
        log.info("Day %d/%d: %d runs ingested, %d feedback so far", day + 1, days + 1, len(day_payloads), total_feedback)
    log.info("Seeded %d runs and %d feedback items", total_runs, total_feedback)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reset", action="store_true", help="drop all data and model artifacts first")
    ap.add_argument("--days", type=int, default=7, help="days of history to simulate")
    ap.add_argument("--runs-per-hour", type=float, default=22.0, help="peak-hour traffic")
    ap.add_argument("--feedback-share", type=float, default=0.4, help="share of flagged runs reviewers label")
    ap.add_argument("--skip-robustness", action="store_true", help="skip leave-one-type-out study (faster)")
    ap.add_argument("--no-history", action="store_true", help="train models only, no simulated traffic")
    ap.add_argument("--seed", type=int, default=2026)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    t0 = time.time()

    if args.reset:
        Base.metadata.drop_all(engine)
        shutil.rmtree(get_settings().artifacts_dir, ignore_errors=True)
        log.info("Reset database and artifacts")
    init_db()
    db = SessionLocal()
    try:
        if training.active_version(db) is not None and not args.reset:
            log.error("A model already exists. Use --reset to rebuild from scratch.")
            sys.exit(1)
        ws_id = ensure_demo_workspace(db)
        register_agents(db, ws_id)
        log.info("Training v1 on simulated reference data (robustness study: %s)...", not args.skip_robustness)
        mv = training.train_new_version(db, "bootstrap", robustness=not args.skip_robustness)
        log.info("v1: macro-F1 %.3f, fused PR-AUC %.3f", mv.macro_f1, mv.pr_auc)
        report = training.warm_start(db)
        log.info("Policy warm start: %s", report.get("final_avg_reward"))

        if not args.no_history:
            seed_history(db, ws_id, args.days, args.runs_per_hour, args.feedback_share, args.seed)
            from app.llm.demo import seed_demo_llm

            n_llm = seed_demo_llm(db, ws_id, days=args.days)
            log.info("Seeded %d simulated LLM calls (tagged 'demo') with contracts, alerts and a drift test", n_llm)
            log.info("Retraining with human labels...")
            mv2 = training.train_new_version(db, "bootstrap: human labels")
            log.info("%s: macro-F1 %.3f (active=%s)", mv2.version, mv2.macro_f1, mv2.active)
    finally:
        db.close()
    log.info("Done in %.0fs. Start the API: uvicorn app.main:app --port 8000", time.time() - t0)
    log.info("The first account you sign up with becomes admin of '%s'.", DEMO_WORKSPACE_NAME)


if __name__ == "__main__":
    main()
