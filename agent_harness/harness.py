"""Instrumented agent harness.

Wraps an agent's tool-calling loop and records every step into a Trace
object. Works with any callable tool set and any policy function, so it can
sit in front of a real LLM-driven agent later -- it ships with a mock tool
set so the whole pipeline is runnable end-to-end without external API keys.
"""
from __future__ import annotations

import random
import time
from typing import Any, Callable, Dict, List

from agent_harness.trace_schema import Step, Trace

PolicyFn = Callable[[List[Step]], Dict[str, Any]]


class Tool:
    """A single callable tool the agent can invoke."""

    def __init__(self, name: str, fn: Callable[..., str], base_latency_ms: float = 120.0):
        self.name = name
        self.fn = fn
        self.base_latency_ms = base_latency_ms

    def call(self, **kwargs: Any) -> Dict[str, Any]:
        start = time.perf_counter()
        output = self.fn(**kwargs)
        elapsed_ms = (time.perf_counter() - start) * 1000.0 + self.base_latency_ms
        tokens = max(8, len(output.split()) * 2)
        return {"output": output, "latency_ms": elapsed_ms, "tokens_used": tokens}


class AgentHarness:
    """Runs a policy function step-by-step and records a full Trace.

    `policy_fn(history)` receives the steps taken so far and must return one of:
        {"action_type": "tool_call", "tool_name": str, "arguments": dict}
        {"action_type": "final_answer", "output": str}
    """

    def __init__(self, tools: Dict[str, Tool], max_steps: int = 20):
        self.tools = tools
        self.max_steps = max_steps

    def run(self, task_description: str, policy_fn: PolicyFn) -> Trace:
        trace = Trace(task_description=task_description)

        for step_id in range(self.max_steps):
            decision = policy_fn(trace.steps)
            action_type = decision.get("action_type", "final_answer")

            if action_type == "final_answer":
                output = decision.get("output", "")
                trace.add_step(
                    Step(
                        step_id=step_id,
                        action_type="final_answer",
                        tool_name=None,
                        arguments={},
                        output=output,
                        latency_ms=random.uniform(50, 150),
                        tokens_used=max(8, len(output.split()) * 2),
                    )
                )
                break

            tool_name = decision["tool_name"]
            arguments = decision.get("arguments", {})
            tool = self.tools.get(tool_name)

            if tool is None:
                trace.add_step(
                    Step(
                        step_id=step_id,
                        action_type="tool_error",
                        tool_name=tool_name,
                        arguments=arguments,
                        output=f"ERROR: unknown tool '{tool_name}'",
                        latency_ms=10.0,
                        tokens_used=10,
                    )
                )
                continue

            result = tool.call(**arguments)
            trace.add_step(
                Step(
                    step_id=step_id,
                    action_type="tool_call",
                    tool_name=tool_name,
                    arguments=arguments,
                    output=result["output"],
                    latency_ms=result["latency_ms"],
                    tokens_used=result["tokens_used"],
                )
            )

        return trace
