"""Deterministic corrections: fix common violations without another model call.

Tried by the gateway in enforcing modes before it asks the model to repair
its answer. A correction is only used if the corrected text passes every
critical rule when checked again.

  * Personal data: emails, phone numbers, card numbers and SSNs are masked.
  * JSON: when a JSON rule fails because the model wrapped the JSON in prose
    or a code fence, the JSON value itself is extracted.
"""
from __future__ import annotations

import json
from typing import List, Optional, Tuple

from .checks import redact
from .evaluator import Evaluation

JSON_RULES = {"json_valid", "json_schema"}
PII_RULES = {"no_pii", "pii_output"}


def extract_json(text: str) -> Optional[str]:
    """The first complete JSON object or array embedded in `text`, if any."""
    decoder = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch not in "{[":
            continue
        try:
            value, end = decoder.raw_decode(text, i)
        except ValueError:
            continue
        if isinstance(value, (dict, list)):
            return text[i:end]
    return None


def autocorrect(contract, text: str, ev: Evaluation) -> Tuple[str, List[str]]:
    """Return (corrected text, list of fixes applied). No fixes -> text unchanged."""
    failed = {c.type for c in ev.checks if not c.passed and not c.skipped}
    fixes: List[str] = []
    out = text
    if getattr(contract, "auto_fix_json", False) and failed & JSON_RULES:
        extracted = extract_json(out)
        if extracted is not None and extracted != out.strip():
            out = extracted
            fixes.append("Extracted the JSON from the surrounding text")
    if getattr(contract, "auto_redact", False) and failed & PII_RULES:
        masked = redact(out)
        if masked != out:
            out = masked
            fixes.append("Masked personal data")
    return out, fixes
