"""Correction prompts: turn a detection into text the agent can act on.

Detection says *what* is going wrong; the policy says *which* intervention
to take. For interventions that continue the run (reflect, retry_step,
escalate_model) the agent needs a concrete message to inject into its
context. This module writes that message from the detected failure type and
the detector evidence, so a correction is specific ("you called
search_docs with the same arguments 4 times at steps 6-9") rather than a
generic "please reconsider".
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

GUIDANCE = {
    "loop": ("You are repeating the same actions without making progress.",
             "Do not repeat a tool call with the same arguments. Summarize what you already know, decide whether "
             "it is enough to answer, and if not, choose a different approach."),
    "tool_thrashing": ("You are switching between tools without using their results.",
                       "Pick the single most relevant tool for the next step, explain in one sentence why, and use its "
                       "output before calling another tool."),
    "hallucinated_tool": ("You called a tool that does not exist.",
                          "Only call tools from the available tool list{tools}. If none fits, answer with what you "
                          "have or ask the user."),
    "token_waste": ("Your responses are much longer than the task needs.",
                    "Be concise: stop restating context, keep tool inputs minimal and give the answer as soon as you "
                    "have it."),
}
CONTINUING_ACTIONS = ("reflect", "retry_step", "escalate_model")


def _steps(evidence: List[int]) -> str:
    s = sorted({i + 1 for i in evidence})  # 1-based, as shown on the run page
    if not s:
        return ""
    if len(s) > 2 and s[-1] - s[0] == len(s) - 1:
        return f" (steps {s[0]}–{s[-1]})"
    return " (step" + ("s " if len(s) > 1 else " ") + ", ".join(map(str, s[:6])) + ")"


def build_correction(failure_type: Optional[str], signals: List[Dict[str, Any]], action: str,
                     tools: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
    """{"action", "prompt", "evidence"} for a continuing intervention, else None."""
    if action not in CONTINUING_ACTIONS or failure_type not in GUIDANCE:
        return None
    relevant = sorted((s for s in signals if s.get("failure_type") == failure_type),
                      key=lambda s: -float(s.get("severity", 0)))[:3]
    evidence = [f"{s['message']}{_steps(s.get('evidence_steps') or [])}" for s in relevant if s.get("message")]
    problem, instruction = GUIDANCE[failure_type]
    tool_list = f" ({', '.join(tools[:20])})" if tools else ""
    lines = [f"[Observability check] {problem}"]
    lines += [f"- {e}" for e in evidence]
    lines.append(instruction.format(tools=tool_list))
    if action == "retry_step":
        lines.append("Redo your last step with these corrections.")
    return {"action": action, "prompt": "\n".join(lines), "evidence": evidence}
