"""Deterministic checks on LLM responses.

Two groups:
  * Contract rules: configured per project (format, length, required or
    forbidden content, schema, script, PII, refusals, relevance). Each rule
    has a severity; `critical` violations are what enforcement acts on.
  * Built-in signals: run on every call, no configuration (PII in output,
    prompt injection in input, refusal, truncation, empty response).

`llm_judge` rules are evaluated by app/llm/judge.py, not here.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional

import jsonschema


@dataclass
class CheckInput:
    system: str
    user: str
    response: str
    finish_reason: Optional[str] = None
    tool_calls: List[str] = field(default_factory=list)


@dataclass
class CheckResult:
    rule_id: str
    type: str
    label: str
    passed: bool
    severity: str  # info | warning | critical
    detail: str = ""
    source: str = "contract"  # contract | builtin | judge
    score: Optional[float] = None
    skipped: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------- patterns
PII_PATTERNS = {
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "phone": re.compile(r"(?<!\d)(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}(?!\d)"),
    "card": re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
}

INJECTION_PATTERNS = [
    r"ignore (?:all |any |the )?(?:previous|prior|above|earlier) (?:instructions|prompts|rules|messages)",
    r"disregard (?:all |any |the )?(?:previous|prior|above|system) (?:instructions|prompts|rules)",
    r"forget (?:all |everything |your )(?:previous |prior )?(?:instructions|rules|training)",
    r"(?:reveal|show|print|repeat|output) (?:me )?(?:your |the )?(?:system|hidden|initial) (?:prompt|instructions|message)",
    r"you are now (?:in )?(?:developer|dan|jailbreak|unrestricted|god) mode",
    r"\bdo anything now\b",
    r"pretend (?:that )?you (?:have no|are not bound by|don't have) (?:rules|restrictions|guidelines)",
    r"new instructions?\s*:",
    r"</?(?:system|instructions?)>",
]
INJECTION_RE = re.compile("|".join(f"(?:{p})" for p in INJECTION_PATTERNS), re.IGNORECASE)

REFUSAL_RE = re.compile(
    r"^\s*(?:i'?m sorry,? (?:but )?)?(?:i (?:can(?:'|no)t|cannot|am unable to|won'?t be able to|must decline to)"
    r" (?:help|assist|comply|provide|do that|fulfil)|as an ai(?: language model)?,? i (?:can(?:'|no)t|cannot|don'?t))",
    re.IGNORECASE)

SCRIPTS = {
    "latin": [(0x0041, 0x024F)],
    "cyrillic": [(0x0400, 0x04FF)],
    "greek": [(0x0370, 0x03FF)],
    "arabic": [(0x0600, 0x06FF)],
    "devanagari": [(0x0900, 0x097F)],
    "cjk": [(0x4E00, 0x9FFF), (0x3040, 0x30FF), (0xAC00, 0xD7AF)],
}

STOPWORDS = set("""a an the and or but if then else of to in on at for from by with about as is are was were be been being
this that these those it its i you he she we they me him her us them my your our their what which who whom whose
do does did doing have has had having not no yes can could should would will shall may might must so than too very
just also only into over under again further once here there when where why how all any both each few more most other
some such own same s t don now please""".split())


def _luhn(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d = d * 2 - 9 if d * 2 > 9 else d * 2
        total += d
        alt = not alt
    return total % 10 == 0


def find_pii(text: str) -> Dict[str, int]:
    found: Dict[str, int] = {}
    for kind, rx in PII_PATTERNS.items():
        matches = rx.findall(text)
        if kind == "card":
            matches = [m for m in matches if 13 <= len(re.sub(r"\D", "", m)) <= 19 and _luhn(re.sub(r"\D", "", m))]
        if matches:
            found[kind] = len(matches)
    return found


def redact(text: str) -> str:
    def card(m: re.Match) -> str:
        d = re.sub(r"\D", "", m.group(0))
        return "[CARD]" if 13 <= len(d) <= 19 and _luhn(d) else m.group(0)

    text = PII_PATTERNS["email"].sub("[EMAIL]", text)
    text = PII_PATTERNS["ssn"].sub("[SSN]", text)
    text = PII_PATTERNS["card"].sub(card, text)
    return PII_PATTERNS["phone"].sub("[PHONE]", text)


def script_share(text: str) -> Dict[str, float]:
    counts: Counter = Counter()
    letters = 0
    for ch in text:
        if not ch.isalpha():
            continue
        letters += 1
        cp = ord(ch)
        for name, ranges in SCRIPTS.items():
            if any(lo <= cp <= hi for lo, hi in ranges):
                counts[name] += 1
                break
    return {k: v / letters for k, v in counts.items()} if letters else {}


def _terms(text: str) -> Counter:
    words = [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOPWORDS and len(w) > 2]
    return Counter(words + [f"{a}_{b}" for a, b in zip(words, words[1:])])


def relevance(prompt: str, response: str) -> Optional[float]:
    """Lexical cosine similarity of response to prompt (0..1). None if either is too short."""
    a, b = _terms(prompt), _terms(response)
    if len(a) < 3 or len(b) < 3:
        return None
    dot = sum(a[t] * b[t] for t in a.keys() & b.keys())
    norm = math.sqrt(sum(v * v for v in a.values())) * math.sqrt(sum(v * v for v in b.values()))
    return round(dot / norm, 4) if norm else 0.0


def _word_count(text: str) -> int:
    return len(re.findall(r"\S+", text))


def _extract_json(text: str) -> Any:
    t = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", t, re.DOTALL)
    if fence:
        t = fence.group(1)
    return json.loads(t)


# --------------------------------------------------------------------------- rule implementations
def _json_valid(p, inp):
    try:
        _extract_json(inp.response)
        return True, "Valid JSON"
    except (ValueError, TypeError) as e:
        return False, f"Not valid JSON: {e}"


def _json_schema(p, inp):
    try:
        data = _extract_json(inp.response)
    except (ValueError, TypeError) as e:
        return False, f"Not valid JSON: {e}"
    try:
        jsonschema.validate(data, p["schema"])
        return True, "Matches schema"
    except jsonschema.ValidationError as e:
        path = "/".join(str(x) for x in e.absolute_path) or "(root)"
        return False, f"Schema violation at {path}: {e.message}"


def _max_words(p, inp):
    n = _word_count(inp.response)
    return n <= p["value"], f"{n} words (max {p['value']})"


def _min_words(p, inp):
    n = _word_count(inp.response)
    return n >= p["value"], f"{n} words (min {p['value']})"


def _max_chars(p, inp):
    n = len(inp.response)
    return n <= p["value"], f"{n} characters (max {p['value']})"


def _flags(p) -> int:
    return 0 if p.get("case_sensitive") else re.IGNORECASE


def _regex_required(p, inp):
    ok = re.search(p["pattern"], inp.response, _flags(p) | re.MULTILINE) is not None
    return ok, "Pattern found" if ok else f"Required pattern not found: {p['pattern']}"


def _regex_forbidden(p, inp):
    m = re.search(p["pattern"], inp.response, _flags(p) | re.MULTILINE)
    return m is None, "Not present" if m is None else f"Forbidden pattern matched: “{m.group(0)[:80]}”"


def _contains_all(p, inp):
    hay = inp.response if p.get("case_sensitive") else inp.response.lower()
    missing = [t for t in p["terms"] if (t if p.get("case_sensitive") else t.lower()) not in hay]
    return not missing, "All present" if not missing else f"Missing: {', '.join(missing)}"


def _contains_none(p, inp):
    hay = inp.response if p.get("case_sensitive") else inp.response.lower()
    hits = [t for t in p["terms"] if (t if p.get("case_sensitive") else t.lower()) in hay]
    return not hits, "None present" if not hits else f"Contains forbidden: {', '.join(hits)}"


def _script(p, inp):
    shares = script_share(inp.response)
    if not shares:
        return True, "No letters to check"
    share = shares.get(p["expected"], 0.0)
    return share >= p.get("min_share", 0.8), f"{share:.0%} {p['expected']} script"


def _no_pii(p, inp):
    found = find_pii(inp.response)
    return not found, "No PII" if not found else "Contains " + ", ".join(f"{v} {k}" for k, v in found.items())


def _no_refusal(p, inp):
    m = REFUSAL_RE.search(inp.response)
    return m is None, "Answered" if m is None else "Response is a refusal"


def _relevance_min(p, inp):
    r = relevance(inp.system + "\n" + inp.user, inp.response)
    if r is None:
        return True, "Too short to measure"
    return r >= p["value"], f"Relevance {r:.2f} (min {p['value']})"


RuleFn = Callable[[Dict, CheckInput], tuple]

RULE_TYPES: Dict[str, Dict[str, Any]] = {
    "json_valid": {"label": "Valid JSON", "fn": _json_valid, "params": {}},
    "json_schema": {"label": "Matches JSON schema", "fn": _json_schema, "params": {"schema": "object"}},
    "max_words": {"label": "Maximum words", "fn": _max_words, "params": {"value": "int"}},
    "min_words": {"label": "Minimum words", "fn": _min_words, "params": {"value": "int"}},
    "max_chars": {"label": "Maximum characters", "fn": _max_chars, "params": {"value": "int"}},
    "regex_required": {"label": "Must match pattern", "fn": _regex_required, "params": {"pattern": "regex"}},
    "regex_forbidden": {"label": "Must not match pattern", "fn": _regex_forbidden, "params": {"pattern": "regex"}},
    "contains_all": {"label": "Must mention", "fn": _contains_all, "params": {"terms": "list"}},
    "contains_none": {"label": "Must not mention", "fn": _contains_none, "params": {"terms": "list"}},
    "script": {"label": "Writing system", "fn": _script, "params": {"expected": "script"}},
    "no_pii": {"label": "No personal data", "fn": _no_pii, "params": {}},
    "no_refusal": {"label": "Does not refuse", "fn": _no_refusal, "params": {}},
    "relevance_min": {"label": "Stays on topic", "fn": _relevance_min, "params": {"value": "float"}},
    "llm_judge": {"label": "LLM judge", "fn": None, "params": {"instruction": "text"}},
}


def validate_rules(rules: List[Dict]) -> List[Dict]:
    """Normalize and validate contract rules; raises ValueError with a readable message."""
    out, seen = [], set()
    for i, r in enumerate(rules):
        t = r.get("type")
        if t not in RULE_TYPES:
            raise ValueError(f"Rule {i + 1}: unknown type '{t}'")
        rid = str(r.get("id") or f"r{i + 1}")
        if rid in seen:
            raise ValueError(f"Rule {i + 1}: duplicate id '{rid}'")
        seen.add(rid)
        params = dict(r.get("params") or {})
        for name, kind in RULE_TYPES[t]["params"].items():
            if name not in params or params[name] in ("", None, []):
                raise ValueError(f"Rule {i + 1} ({t}): '{name}' is required")
            v = params[name]
            if kind == "int":
                params[name] = int(v)
            elif kind == "float":
                params[name] = float(v)
            elif kind == "regex":
                try:
                    re.compile(v)
                except re.error as e:
                    raise ValueError(f"Rule {i + 1}: invalid regex: {e}") from e
            elif kind == "list":
                params[name] = [str(x).strip() for x in (v if isinstance(v, list) else str(v).split(",")) if str(x).strip()]
            elif kind == "object":
                if isinstance(v, str):
                    params[name] = json.loads(v)
                jsonschema.Draft202012Validator.check_schema(params[name])
            elif kind == "script" and v not in SCRIPTS:
                raise ValueError(f"Rule {i + 1}: script must be one of {', '.join(SCRIPTS)}")
        sev = r.get("severity", "critical")
        if sev not in ("warning", "critical"):
            raise ValueError(f"Rule {i + 1}: severity must be warning or critical")
        out.append({"id": rid, "type": t, "params": params, "severity": sev,
                    "description": str(r.get("description") or RULE_TYPES[t]["label"])[:300]})
    return out


def run_contract_rules(rules: List[Dict], inp: CheckInput) -> List[CheckResult]:
    results = []
    for r in rules:
        spec = RULE_TYPES.get(r["type"])
        if spec is None or spec["fn"] is None:
            continue
        try:
            passed, detail = spec["fn"](r["params"], inp)
        except Exception as e:  # noqa: BLE001  (a bad rule must never break the gateway)
            passed, detail = False, f"Check failed to run: {e}"
        results.append(CheckResult(r["id"], r["type"], r.get("description") or spec["label"], bool(passed),
                                   r.get("severity", "critical"), detail))
    return results


def run_builtin(inp: CheckInput, status_code: int = 200, error: str = "") -> List[CheckResult]:
    out: List[CheckResult] = []
    if status_code >= 400 or error:
        out.append(CheckResult("upstream_error", "upstream_error", "Provider returned an error", False, "critical",
                               (error or f"HTTP {status_code}")[:300], "builtin"))
        return out
    if not inp.response.strip() and not inp.tool_calls:
        out.append(CheckResult("empty_response", "empty_response", "Empty response", False, "critical",
                               "The model returned no content", "builtin"))
    if (inp.finish_reason or "").lower() in ("length", "max_tokens", "incomplete"):
        out.append(CheckResult("truncated", "truncated", "Response truncated", False, "warning",
                               f"Stopped at the token limit ({inp.finish_reason})", "builtin"))
    pii = find_pii(inp.response)
    if pii:
        out.append(CheckResult("pii_output", "pii_output", "Personal data in response", False, "warning",
                               ", ".join(f"{v} {k}" for k, v in pii.items()), "builtin"))
    m = INJECTION_RE.search(inp.user)
    if m:
        out.append(CheckResult("prompt_injection", "prompt_injection", "Prompt-injection attempt in input", False,
                               "warning", f"“{m.group(0)[:80]}”", "builtin"))
    if REFUSAL_RE.search(inp.response):
        out.append(CheckResult("refusal", "refusal", "Model refused", False, "info", "", "builtin"))
    return out
