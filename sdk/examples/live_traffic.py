"""Stream simulated agent runs to the API step by step, acting on interventions.

    python sdk/examples/live_traffic.py --runs 50 --delay 0.3

Shows how an agent loop uses the SDK: after every step it receives the live
risk assessment and stops when the policy recommends terminating or paging a
human. Keep the dashboard open to watch runs arrive.
"""
from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "sdk"))
sys.path.insert(0, str(ROOT / "backend"))  # only for the traffic simulator

from agent_observability import ObservabilityClient  # noqa: E402
from ml.simulator import generate_run  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--api-key", default="dev-local-key")
    ap.add_argument("--runs", type=int, default=30)
    ap.add_argument("--delay", type=float, default=0.25, help="seconds between steps")
    ap.add_argument("--failure-scale", type=float, default=2.0, help="multiply failure rates for a livelier demo")
    args = ap.parse_args()

    client = ObservabilityClient(args.url, args.api_key, fail_open=False)
    rng = random.Random()
    for i in range(args.runs):
        sim = generate_run(rng, failure_scale=args.failure_scale)
        with client.run(sim.agent_id, task=sim.task, model=sim.model) as run:
            verdict = None
            for step in sim.steps:
                payload = dict(input_tokens=step.input_tokens, output_tokens=step.output_tokens,
                               latency_ms=step.latency_ms)
                if step.type == "tool_call":
                    verdict = run.tool_call(step.tool_name, step.arguments, step.output,
                                            error=step.status == "error", **payload)
                elif step.type == "llm":
                    verdict = run.reasoning(step.output, **payload)
                else:
                    verdict = run.final_answer(step.output, **payload)
                time.sleep(args.delay)
                if verdict and verdict.should_stop:
                    break
        v = verdict
        stopped = " -> STOPPED" if v and v.should_stop else ""
        print(f"[{i + 1:>3}] {sim.agent_id:<18} truth={sim.source_label:<17} "
              f"risk={v.risk_score:.2f} {v.severity:<8} {v.failure_type or '-':<17} action={v.action}{stopped}")


if __name__ == "__main__":
    main()
