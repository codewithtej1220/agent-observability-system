"""Evaluate one LLM response against built-in signals, its contract, and the judge."""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from ..orm import Workspace
from ..orm_llm import Contract
from .checks import CheckInput, CheckResult, relevance, run_builtin, run_contract_rules
from .judge import SYSTEM_RULE_ID, SYSTEM_RULE_TEXT, judge_config, run_judge


@dataclass
class Evaluation:
    checks: List[CheckResult] = field(default_factory=list)
    judge_cost: float = 0.0
    relevance: Optional[float] = None
    judge_pending: bool = False  # judge rules exist but were not run (e.g. enforcement without judge)

    @property
    def rule_results(self) -> List[CheckResult]:
        return [c for c in self.checks if c.source in ("contract", "judge") and not c.skipped]

    @property
    def violations(self) -> List[CheckResult]:
        return [c for c in self.rule_results if not c.passed]

    @property
    def critical_violations(self) -> List[CheckResult]:
        return [c for c in self.violations if c.severity == "critical"]

    @property
    def adherence(self) -> Optional[float]:
        r = self.rule_results
        return round(sum(c.passed for c in r) / len(r), 4) if r else None

    @property
    def judge_score(self) -> Optional[float]:
        s = [c.score for c in self.checks if c.source == "judge" and c.score is not None and not c.skipped]
        return round(sum(s) / len(s), 4) if s else None

    @property
    def severity(self) -> str:
        failed = [c for c in self.checks if not c.passed and not c.skipped]
        if any(c.severity == "critical" for c in failed):
            return "critical"
        if any(c.severity == "warning" for c in failed):
            return "warning"
        return "ok"

    def has(self, rule_id: str) -> bool:
        return any(c.rule_id == rule_id and not c.passed for c in self.checks)

    def violation_message(self) -> str:
        return "\n".join(f"- {c.label}: {c.detail}" for c in self.critical_violations)


async def evaluate(db: Session, ws: Workspace, contract: Optional[Contract], inp: CheckInput, *,
                   use_judge: bool = True, status_code: int = 200, error: str = "",
                   force_auto_judge: bool = False) -> Evaluation:
    ev = Evaluation()
    ev.checks.extend(run_builtin(inp, status_code, error))
    if status_code >= 400 or error:
        return ev
    ev.relevance = relevance(inp.system + "\n" + inp.user, inp.response)

    rules = list(contract.rules) if contract and contract.active else []
    ev.checks.extend(run_contract_rules(rules, inp))

    judge_rules = [(r["id"], r["params"]["instruction"]) for r in rules if r["type"] == "llm_judge"]
    severities: Dict[str, str] = {r["id"]: r.get("severity", "critical") for r in rules}
    labels: Dict[str, str] = {r["id"]: r.get("description") or "LLM judge" for r in rules}
    auto = (not judge_rules and inp.system.strip() and ws.setting("auto_judge")
            and (force_auto_judge or random.random() < float(ws.setting("judge_sample_rate") or 0)))
    if auto:
        judge_rules = [(SYSTEM_RULE_ID, SYSTEM_RULE_TEXT)]
        severities[SYSTEM_RULE_ID], labels[SYSTEM_RULE_ID] = "warning", "Follows the system prompt"

    if judge_rules:
        if not use_judge:
            ev.judge_pending = True
        elif judge_config(db, ws) is None:
            for rid, _ in judge_rules:
                ev.checks.append(CheckResult(rid, "llm_judge", labels[rid], True, severities[rid],
                                             "Skipped: no judge configured", "judge", skipped=True))
        else:
            verdicts, cost, err = await run_judge(db, ws, judge_rules, inp)
            ev.judge_cost = cost
            for rid, _ in judge_rules:
                v = verdicts.get(rid)
                if v is None:
                    ev.checks.append(CheckResult(rid, "llm_judge", labels[rid], True, severities[rid],
                                                 f"Skipped: {err or 'no verdict returned'}", "judge", skipped=True))
                else:
                    ev.checks.append(CheckResult(rid, "llm_judge", labels[rid], v.passed, severities[rid],
                                                 v.reason, "judge", score=v.score))
    return ev
