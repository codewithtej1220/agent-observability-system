from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

STOP_ACTIONS = {"terminate", "human_review"}


class ObservabilityError(RuntimeError):
    pass


@dataclass
class Assessment:
    run_id: str
    step_count: int
    risk_score: float
    severity: str
    failure_type: Optional[str]
    action: str
    action_label: str
    reason: str
    signals: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def should_stop(self) -> bool:
        """True when the policy recommends halting the agent loop."""
        return self.action in STOP_ACTIONS

    @property
    def flagged(self) -> bool:
        return self.severity != "healthy"

    @classmethod
    def from_json(cls, d: Dict[str, Any]) -> "Assessment":
        return cls(
            run_id=d["run_id"], step_count=d["step_count"], risk_score=d["risk_score"], severity=d["severity"],
            failure_type=d.get("failure_type"), action=d["recommended_action"], action_label=d["action_label"],
            reason=d.get("action_reason", ""), signals=d.get("signals", []),
        )


class ObservabilityClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8000", api_key: str = "dev-local-key",
                 timeout: float = 10.0, fail_open: bool = True):
        """
        fail_open: if the observability service is unreachable, keep the agent
        running (step calls return None) instead of raising. Monitoring should
        never take production down.
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.fail_open = fail_open

    def _request(self, method: str, path: str, body: Optional[Dict] = None) -> Any:
        data = json.dumps(body, default=str).encode() if body is not None else None
        req = urllib.request.Request(
            f"{self.base_url}{path}", data=data, method=method,
            headers={"X-API-Key": self.api_key, "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read() or b"null")
        except urllib.error.HTTPError as e:
            raise ObservabilityError(f"{e.code} {e.reason}: {e.read().decode(errors='replace')}") from e
        except (urllib.error.URLError, TimeoutError) as e:
            raise ObservabilityError(f"Cannot reach {self.base_url}: {e}") from e

    # -- agents ----------------------------------------------------------
    def register_agent(self, agent_id: str, tools: Optional[List[str]] = None, name: str = "",
                       model: str = "", framework: str = "", description: str = "") -> Dict:
        """Registering tools lets the service flag hallucinated tool calls exactly."""
        return self._request("POST", "/api/agents", {
            "id": agent_id, "name": name or agent_id, "model": model, "framework": framework,
            "description": description, "registered_tools": tools,
        })

    # -- runs ------------------------------------------------------------
    def run(self, agent_id: str, task: str = "", model: str = "", run_id: Optional[str] = None) -> "LiveRun":
        return LiveRun(self, agent_id, task, model, run_id)

    def ingest_run(self, run: Dict) -> Assessment:
        """Send a completed run in one call (post-hoc analysis)."""
        return Assessment.from_json(self._request("POST", "/api/ingest/runs", run))

    def feedback(self, run_id: str, label: str, resolved: bool, action_taken: Optional[str] = None,
                 notes: str = "", reviewer: str = "") -> Dict:
        """Close the loop: report the true condition and outcome of a run."""
        return self._request("POST", f"/api/runs/{run_id}/feedback", {
            "label": label, "resolved": resolved, "action_taken": action_taken, "notes": notes, "reviewer": reviewer,
        })


class LiveRun:
    """A run streamed step by step. Use as a context manager."""

    def __init__(self, client: ObservabilityClient, agent_id: str, task: str, model: str, run_id: Optional[str]):
        self.client = client
        self.agent_id = agent_id
        self.task = task
        self.model = model
        self.run_id = run_id
        self.last: Optional[Assessment] = None
        self._disabled = False

    def __enter__(self) -> "LiveRun":
        try:
            d = self.client._request("POST", "/api/ingest/runs/start", {
                "run_id": self.run_id, "agent_id": self.agent_id, "task": self.task, "model": self.model,
            })
            self.run_id = d["run_id"]
        except ObservabilityError:
            if not self.client.fail_open:
                raise
            self._disabled = True
        return self

    def __exit__(self, *exc) -> None:
        if not self._disabled and self.run_id:
            try:
                self.client._request("POST", f"/api/ingest/runs/{self.run_id}/finish")
            except ObservabilityError:
                if not self.client.fail_open:
                    raise

    def _step(self, step: Dict) -> Optional[Assessment]:
        if self._disabled:
            return None
        try:
            self.last = Assessment.from_json(self.client._request("POST", f"/api/ingest/runs/{self.run_id}/steps", step))
            return self.last
        except ObservabilityError:
            if not self.client.fail_open:
                raise
            return None

    def tool_call(self, tool_name: str, arguments: Dict[str, Any], output: str, error: bool = False,
                  latency_ms: Optional[float] = None, input_tokens: int = 0, output_tokens: int = 0,
                  started: Optional[float] = None) -> Optional[Assessment]:
        if latency_ms is None and started is not None:
            latency_ms = (time.perf_counter() - started) * 1000
        return self._step({
            "type": "tool_call", "tool_name": tool_name, "arguments": arguments, "output": str(output),
            "status": "error" if error else "ok", "latency_ms": latency_ms or 0.0,
            "input_tokens": input_tokens, "output_tokens": output_tokens,
        })

    def reasoning(self, text: str, input_tokens: int = 0, output_tokens: int = 0,
                  latency_ms: float = 0.0) -> Optional[Assessment]:
        return self._step({"type": "llm", "output": text, "input_tokens": input_tokens,
                           "output_tokens": output_tokens, "latency_ms": latency_ms})

    def final_answer(self, text: str, input_tokens: int = 0, output_tokens: int = 0,
                     latency_ms: float = 0.0) -> Optional[Assessment]:
        return self._step({"type": "final_answer", "output": text, "input_tokens": input_tokens,
                           "output_tokens": output_tokens, "latency_ms": latency_ms})
