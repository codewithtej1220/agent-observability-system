"""LLM-as-judge for rules that cannot be checked deterministically.

All judge rules for one response are evaluated in a single call to keep cost
and latency down. The judge model and credential are workspace settings, so
you can judge an expensive model with a cheap one (or with a different
provider, which avoids a model grading its own homework).

Judges make mistakes too: judge results show up in the dashboard with their
reasons, and should be spot-checked.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from ..orm import ProviderCredential, Workspace
from ..pricing import estimate_cost
from .checks import CheckInput
from .providers import estimate_tokens, get_adapter
from .upstream import call_json, credential_key

log = logging.getLogger(__name__)

DEFAULT_JUDGE_MODELS = {"openai": "gpt-4o-mini", "anthropic": "claude-haiku-4-5", "gemini": "gemini-3.5-flash"}
SYSTEM_RULE_ID = "system_prompt"
SYSTEM_RULE_TEXT = "The response follows every instruction in the system prompt (tone, scope, format, restrictions)."

JUDGE_SYSTEM = """You are a strict, impartial evaluator of AI assistant responses.
For each rule, decide whether the RESPONSE satisfies it, given the SYSTEM PROMPT and USER MESSAGE as context.
Judge only what is asked. If a rule does not apply to this exchange, it passes.
Reply with JSON only, no prose, in exactly this shape:
{"results": [{"id": "<rule id>", "pass": true|false, "score": <0.0-1.0 compliance>, "reason": "<one short sentence>"}]}"""


@dataclass
class JudgeVerdict:
    passed: bool
    score: float
    reason: str


def _clip(text: str, n: int) -> str:
    return text if len(text) <= n else text[: n // 2] + "\n…[truncated]…\n" + text[-n // 2:]


def build_prompt(rules: List[Tuple[str, str]], inp: CheckInput) -> str:
    listed = "\n".join(f'- id "{rid}": {text}' for rid, text in rules)
    return (f"RULES:\n{listed}\n\n<SYSTEM PROMPT>\n{_clip(inp.system, 6000) or '(none)'}\n</SYSTEM PROMPT>\n\n"
            f"<USER MESSAGE>\n{_clip(inp.user, 6000)}\n</USER MESSAGE>\n\n<RESPONSE>\n{_clip(inp.response, 8000)}\n</RESPONSE>")


def parse_verdicts(text: str, ids: List[str]) -> Dict[str, JudgeVerdict]:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError("Judge did not return JSON")
    data = json.loads(m.group(0))
    out = {}
    for item in data.get("results", []):
        rid = str(item.get("id"))
        if rid in ids:
            passed = bool(item.get("pass"))
            score = float(item.get("score", 1.0 if passed else 0.0))
            out[rid] = JudgeVerdict(passed, max(0.0, min(1.0, score)), str(item.get("reason", ""))[:300])
    return out


def judge_config(db: Session, ws: Workspace) -> Optional[Tuple[ProviderCredential, str]]:
    cred_id = ws.setting("judge_credential_id")
    if not cred_id:
        return None
    cred = db.get(ProviderCredential, cred_id)
    if cred is None or cred.workspace_id != ws.id:
        return None
    return cred, ws.setting("judge_model") or DEFAULT_JUDGE_MODELS[cred.provider]


async def run_judge(db: Session, ws: Workspace, rules: List[Tuple[str, str]],
                    inp: CheckInput) -> Tuple[Dict[str, JudgeVerdict], float, Optional[str]]:
    """Returns (verdicts by rule id, judge cost USD, error message or None)."""
    cfg = judge_config(db, ws)
    if cfg is None:
        return {}, 0.0, "No judge configured (Settings → LLM judge)"
    cred, model = cfg
    adapter = get_adapter(cred.provider)
    prompt = build_prompt(rules, inp)
    path, body = adapter.simple_request(model, JUDGE_SYSTEM, prompt, max_tokens=200 + 80 * len(rules))
    try:
        status, data, _ = await call_json(cred.provider, credential_key(db, cred), path, body)
    except Exception as e:  # noqa: BLE001
        log.warning("Judge call failed: %s", e)
        return {}, 0.0, f"Judge call failed: {e}"
    if status >= 400 or not isinstance(data, dict):
        return {}, 0.0, f"Judge provider returned HTTP {status}"
    c = adapter.parse_response(path, data)
    cost = estimate_cost(model, c.input_tokens or estimate_tokens(JUDGE_SYSTEM + prompt),
                         c.output_tokens or estimate_tokens(c.text))
    try:
        return parse_verdicts(c.text, [r for r, _ in rules]), cost, None
    except (ValueError, json.JSONDecodeError) as e:
        return {}, cost, f"Could not parse judge output: {e}"
