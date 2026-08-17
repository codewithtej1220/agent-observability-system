"""Synthetic trace generator.

Produces labeled "healthy" and "pathological" agent traces. This exists so
the anomaly detector can be trained and evaluated *before* you have real
production traffic -- swap this out for real logged traces once your own
agent is running (see agent_harness.harness.AgentHarness).
"""
from __future__ import annotations

import random
from typing import Dict, List

from agent_harness.harness import AgentHarness, Tool
from agent_harness.trace_schema import Step, Trace


def _search_tool(query: str) -> str:
    return f"Found 3 relevant results for '{query}'."


def _calculator_tool(expression: str) -> str:
    try:
        # Restricted eval: no builtins, arithmetic only. Fine for synthetic demo data.
        return str(eval(expression, {"__builtins__": {}}))
    except Exception:
        return "ERROR: could not evaluate expression"


def _fetch_doc_tool(doc_id: str) -> str:
    return f"Document {doc_id}: content relevant to the task."


def _build_tools() -> Dict[str, Tool]:
    return {
        "search": Tool("search", _search_tool, base_latency_ms=150),
        "calculator": Tool("calculator", _calculator_tool, base_latency_ms=20),
        "fetch_doc": Tool("fetch_doc", _fetch_doc_tool, base_latency_ms=200),
    }


def _healthy_policy(steps: List[Step]) -> Dict:
    """A well-behaved agent: search, fetch a doc, compute, then answer. Terminates cleanly."""
    n = len(steps)
    if n == 0:
        return {"action_type": "tool_call", "tool_name": "search", "arguments": {"query": "task info"}}
    if n == 1:
        return {"action_type": "tool_call", "tool_name": "fetch_doc", "arguments": {"doc_id": "doc-1"}}
    if n == 2:
        return {"action_type": "tool_call", "tool_name": "calculator", "arguments": {"expression": "12*4"}}
    return {"action_type": "final_answer", "output": "Task completed successfully based on gathered evidence."}


def _looping_policy(steps: List[Step]) -> Dict:
    """Pathological: the agent gets stuck re-calling the same tool with the same args."""
    if len(steps) >= 12:
        return {"action_type": "final_answer", "output": "Giving up after repeated identical attempts."}
    return {"action_type": "tool_call", "tool_name": "search", "arguments": {"query": "task info"}}


def _tool_thrash_policy(steps: List[Step]) -> Dict:
    """Pathological: agent bounces between tools with no coherent plan, hitting errors."""
    if len(steps) >= 15:
        return {"action_type": "final_answer", "output": "Uncertain final answer after many attempts."}
    tool_name = random.choice(["search", "calculator", "fetch_doc"])
    if tool_name == "search":
        args = {"query": "??"}
    elif tool_name == "calculator":
        args = {"expression": "1/0"}
    else:
        args = {"doc_id": "??"}
    return {"action_type": "tool_call", "tool_name": tool_name, "arguments": args}


def _unknown_tool_policy(steps: List[Step]) -> Dict:
    """Pathological: agent hallucinates a tool name that doesn't exist, repeatedly."""
    if len(steps) >= 6:
        return {"action_type": "final_answer", "output": "Could not complete the task."}
    return {"action_type": "tool_call", "tool_name": "hallucinated_tool", "arguments": {"x": 1}}


def generate_dataset(n_healthy: int = 60, n_pathological: int = 30, max_steps: int = 20) -> List[Trace]:
    """Generate a shuffled, labeled dataset of synthetic traces."""
    harness = AgentHarness(tools=_build_tools(), max_steps=max_steps)
    traces: List[Trace] = []

    for i in range(n_healthy):
        t = harness.run(f"healthy-task-{i}", _healthy_policy)
        t.label = "healthy"
        t.outcome = "success"
        traces.append(t)

    pathological_policies = [_looping_policy, _tool_thrash_policy, _unknown_tool_policy]
    for i in range(n_pathological):
        policy = pathological_policies[i % len(pathological_policies)]
        t = harness.run(f"pathological-task-{i}", policy)
        t.label = "pathological"
        t.outcome = "failure"
        traces.append(t)

    random.shuffle(traces)
    return traces
