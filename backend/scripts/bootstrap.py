"""Bootstrap a working system from real data.

    python -m scripts.fetch_real_traces              (once: download the real agent traces)
    python -m scripts.bootstrap                      (from backend/)
    python -m scripts.bootstrap --reset              wipe database and artifacts first
    python -m scripts.bootstrap --import-runs 400    also show held-out real runs on the dashboard

Steps:
  1. Train model v1 on real agent runs (SWE-agent trajectories, see
     ml/real_traces.py); evaluate on held-out runs of different GitHub issues,
     including the leave-one-failure-type-out robustness study.
  2. Start the intervention policy from zero: it follows the failure-type
     playbook until it has learned from enough reviewed outcomes.
  3. Optionally replay held-out real runs through the normal ingestion path so
     the agent pages have something to show. They are tagged with their source
     and get timestamps spread over the last few days (the dataset has none).

No traffic is simulated. Point your own agents (sdk/) and apps (the LLM
gateway or browser extension) at the API to fill the dashboards.
"""
from __future__ import annotations

import argparse
import logging
import shutil
import sys
import time
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.db import Base, SessionLocal, engine, init_db  # noqa: E402
from app.auth import DEMO_WORKSPACE_NAME, demo_workspace  # noqa: E402
from app.orm import DEFAULT_WORKSPACE_SETTINGS, Agent, Workspace, utcnow  # noqa: E402
from app.schemas import RunIn, StepIn  # noqa: E402
from app.services import ingest, training  # noqa: E402
from app.services.registry import registry  # noqa: E402
from ml import real_traces  # noqa: E402
from ml.schema import Run  # noqa: E402

log = logging.getLogger("bootstrap")

PUBLIC_AGENTS = {
    "swe-agent-llama-8b": "SWE-agent · Llama 3.1 8B",
    "swe-agent-llama-70b": "SWE-agent · Llama 3.1 70B",
    "swe-agent-llama-405b": "SWE-agent · Llama 3.1 405B",
}


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
    if ws.plan != "internal":  # the platform owner's demo workspace is never limited
        ws.plan, ws.plan_status = "internal", "active"
    db.commit()
    return ws.id


def import_public_runs(db, ws_id: int, n: int, hours: int = 72) -> int:
    """Replay `n` held-out real runs through ingestion (scored by the trained model)."""
    _, _, test = training.reference_data()
    runs = test[:n]
    if not runs:
        return 0
    known = registry.engine.known_tools if registry.engine else {}
    for agent_id in {r.agent_id for r in runs}:
        row = db.get(Agent, (ws_id, agent_id)) or Agent(workspace_id=ws_id, id=agent_id)
        row.name = PUBLIC_AGENTS.get(agent_id, agent_id)
        row.description = "Public SWE-agent traces (CC BY 4.0): fixes GitHub issues"
        row.model, row.framework = agent_id.removeprefix("swe-agent-"), "SWE-agent"
        row.registered_tools = sorted(known.get(agent_id, [])) or None
        db.add(row)
    db.commit()
    now = utcnow()
    span = timedelta(hours=hours)
    payloads = [run_to_payload(r, now - span + span * (i + 0.5) / len(runs)) for i, r in enumerate(runs)]
    for i in range(0, len(payloads), 200):
        ingest.ingest_runs(db, ws_id, payloads[i:i + 200])
    return len(payloads)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reset", action="store_true", help="drop all data and model artifacts first")
    ap.add_argument("--skip-robustness", action="store_true", help="skip leave-one-type-out study (faster)")
    ap.add_argument("--import-runs", type=int, default=0, metavar="N",
                    help="replay N held-out real runs into the demo workspace (default 0)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    t0 = time.time()

    if not real_traces.available(training.DATA_DIR):
        log.error("Real agent traces are missing. Download them first: python -m scripts.fetch_real_traces")
        sys.exit(1)
    if args.reset:
        Base.metadata.drop_all(engine)
        with engine.begin() as conn:  # so migrations re-create everything from scratch
            conn.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
        shutil.rmtree(get_settings().artifacts_dir, ignore_errors=True)
        log.info("Reset database and artifacts")
    init_db()
    db = SessionLocal()
    try:
        if training.active_version(db) is not None and not args.reset:
            log.error("A model already exists. Use --reset to rebuild from scratch.")
            sys.exit(1)
        ws_id = ensure_demo_workspace(db)
        log.info("Training v1 on real agent runs (robustness study: %s)...", not args.skip_robustness)
        mv = training.train_new_version(db, "bootstrap: real traces", robustness=not args.skip_robustness)
        log.info("v1: macro-F1 %.3f, fused PR-AUC %.3f", mv.macro_f1, mv.pr_auc)
        training.reset_policy(db)
        if args.import_runs:
            n = import_public_runs(db, ws_id, args.import_runs)
            log.info("Replayed %d held-out real runs into '%s'", n, DEMO_WORKSPACE_NAME)
    finally:
        db.close()
    log.info("Done in %.0fs. Start the API: uvicorn app.main:app --port 8000", time.time() - t0)
    log.info("The first account you sign up with becomes admin of '%s'.", DEMO_WORKSPACE_NAME)


if __name__ == "__main__":
    main()
