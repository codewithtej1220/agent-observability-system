"""Agent traffic simulator.

Generates realistic agent runs for bootstrapping and evaluating the models
before (or alongside) real production traffic. Design goals:

* Several agents with different tools, base prompts, and failure tendencies,
  so per-agent baselines and agent comparison are meaningful.
* Failures begin *mid-run* (after a healthy prefix) and the onset step is
  recorded, so early-detection latency can be measured.
* Hard negatives: healthy runs that superficially resemble failures
  (pagination, retry-after-transient-error, productive A/B alternation,
  long-but-productive runs). Without these, any rule would score 100%.
* Context accumulates, so input tokens grow with run length -- the cost of a
  loop is super-linear, as it is in real agents.

Also provides an outcome model used to simulate feedback for the
intervention policy (what happens if action X is taken on failure Y).
"""
from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from .schema import Run, Step

WORD_BANK = (
    "account invoice refund shipment delayed warehouse customer premium subscription "
    "renewal policy exception approved pending escalated priority region europe asia "
    "quarterly revenue margin forecast churn cohort retention pipeline latency error "
    "timeout deployment branch commit test failing passing coverage module function "
    "parameter config schema migration index query table column join aggregate metric "
    "flight hotel itinerary layover departure arrival visa currency exchange weather "
    "forecast rain sunny temperature budget booking confirmed cancelled vendor contract "
    "clause liability payment terms net30 net60 audit compliance gdpr retention record "
    "source citation study paper author journal findings sample dataset benchmark model "
    "accuracy baseline variance hypothesis evidence summary conclusion section chapter "
    "release version patch security vulnerability dependency upgrade rollback incident "
    "outage capacity cluster node replica shard backup restore ticket status resolved "
    "open closed assigned agent team manager tier discount coupon cart checkout address "
    "warranty repair replacement defect serial batch supplier lead quote estimate total"
).split()


@dataclass
class ToolSpec:
    name: str
    arg_keys: List[str]
    latency_ms: float
    output_tokens: Tuple[int, int]  # tokens of tool output added to context


@dataclass
class AgentProfile:
    agent_id: str
    name: str
    description: str
    model: str
    framework: str
    base_prompt_tokens: int
    tools: List[ToolSpec]
    workflows: List[List[str]]
    fake_tools: List[str]
    failure_rates: Dict[str, float]
    traffic_weight: float = 1.0
    alternation_pair: Optional[Tuple[str, str]] = None
    paginated_tool: Optional[str] = None

    @property
    def tool_names(self) -> List[str]:
        return [t.name for t in self.tools]

    def tool(self, name: str) -> ToolSpec:
        for t in self.tools:
            if t.name == name:
                return t
        raise KeyError(name)


def _t(name, keys, lat, toks=(60, 300)):
    return ToolSpec(name, keys, lat, toks)


AGENTS: List[AgentProfile] = [
    AgentProfile(
        "support-bot", "Customer Support Bot", "Resolves customer tickets: orders, refunds, account questions.",
        "gpt-4o-mini", "LangGraph", 1400,
        [_t("search_kb", ["query"], 180), _t("get_customer", ["customer_id"], 90, (40, 120)),
         _t("get_order", ["order_id"], 110, (50, 160)), _t("issue_refund", ["order_id", "amount"], 240, (20, 60)),
         _t("update_ticket", ["ticket_id", "status"], 120, (15, 40)), _t("send_reply", ["ticket_id", "message"], 150, (15, 40))],
        [["get_customer", "get_order", "search_kb", "send_reply"],
         ["search_kb", "send_reply", "update_ticket"],
         ["get_order", "issue_refund", "send_reply", "update_ticket"],
         ["get_customer", "search_kb", "search_kb", "send_reply"]],
        ["get_order_history", "lookup_customer_v2", "refund_order", "check_inventory"],
        {"loop": 0.04, "tool_thrashing": 0.03, "hallucinated_tool": 0.05, "token_waste": 0.02},
        traffic_weight=2.2, paginated_tool="search_kb",
    ),
    AgentProfile(
        "research-agent", "Research Assistant", "Answers research questions with web sources and citations.",
        "claude-sonnet-4-5", "Custom loop", 2200,
        [_t("web_search", ["query"], 650, (150, 500)), _t("fetch_url", ["url"], 900, (400, 1400)),
         _t("extract_facts", ["url", "question"], 300, (80, 250)), _t("summarize", ["text_ref"], 400, (100, 300)),
         _t("cite_sources", ["refs"], 120, (40, 120))],
        [["web_search", "fetch_url", "extract_facts", "summarize", "cite_sources"],
         ["web_search", "fetch_url", "extract_facts", "fetch_url", "extract_facts", "summarize", "cite_sources"],
         ["web_search", "web_search", "fetch_url", "summarize"]],
        ["search_arxiv", "browse_page", "get_citations", "pdf_reader"],
        {"loop": 0.09, "tool_thrashing": 0.03, "hallucinated_tool": 0.03, "token_waste": 0.05},
        traffic_weight=1.4, alternation_pair=("fetch_url", "extract_facts"), paginated_tool="web_search",
    ),
    AgentProfile(
        "code-assistant", "Code Assistant", "Edits a repository, runs tests and proposes patches.",
        "claude-opus-4-1", "OpenAI Agents SDK", 3200,
        [_t("grep_repo", ["pattern"], 140, (100, 400)), _t("read_file", ["path"], 60, (300, 1200)),
         _t("write_file", ["path", "patch"], 80, (20, 60)), _t("run_tests", ["target"], 4200, (150, 600)),
         _t("git_diff", [], 90, (100, 400))],
        [["grep_repo", "read_file", "write_file", "run_tests", "git_diff"],
         ["read_file", "read_file", "write_file", "run_tests"],
         ["grep_repo", "read_file", "write_file", "run_tests", "write_file", "run_tests", "git_diff"]],
        ["apply_patch", "search_code", "execute_shell", "lint_file"],
        {"loop": 0.05, "tool_thrashing": 0.04, "hallucinated_tool": 0.04, "token_waste": 0.08},
        traffic_weight=1.2, alternation_pair=("write_file", "run_tests"),
    ),
    AgentProfile(
        "data-analyst", "Data Analyst", "Answers business questions with SQL and Python over the warehouse.",
        "gpt-4.1", "LangChain", 1800,
        [_t("list_tables", [], 200, (60, 200)), _t("describe_table", ["table"], 180, (80, 300)),
         _t("sql_query", ["sql"], 1200, (100, 600)), _t("python_exec", ["code"], 900, (50, 300)),
         _t("plot_chart", ["spec"], 500, (20, 60))],
        [["list_tables", "describe_table", "sql_query", "plot_chart"],
         ["describe_table", "sql_query", "python_exec", "plot_chart"],
         ["list_tables", "describe_table", "describe_table", "sql_query", "sql_query", "python_exec"]],
        ["run_query", "get_schema", "export_csv", "pandas_eval"],
        {"loop": 0.04, "tool_thrashing": 0.09, "hallucinated_tool": 0.04, "token_waste": 0.03},
        traffic_weight=1.0, paginated_tool="sql_query",
    ),
    AgentProfile(
        "travel-planner", "Travel Planner", "Plans trips: flights, hotels, weather, and itineraries.",
        "gemini-2.5-flash", "CrewAI", 1200,
        [_t("search_flights", ["origin", "destination", "date"], 1100, (200, 600)),
         _t("search_hotels", ["city", "checkin", "nights"], 900, (200, 600)),
         _t("get_weather", ["city", "date"], 250, (40, 120)), _t("convert_currency", ["amount", "from", "to"], 90, (15, 40)),
         _t("create_itinerary", ["items"], 300, (100, 300))],
        [["search_flights", "search_hotels", "get_weather", "create_itinerary"],
         ["get_weather", "search_hotels", "convert_currency", "create_itinerary"],
         ["search_flights", "search_flights", "search_hotels", "convert_currency", "create_itinerary"]],
        ["book_flight", "get_visa_requirements", "search_restaurants", "rent_car"],
        {"loop": 0.03, "tool_thrashing": 0.03, "hallucinated_tool": 0.10, "token_waste": 0.02},
        traffic_weight=0.9,
    ),
    AgentProfile(
        "invoice-processor", "Invoice Processor", "Extracts and validates invoice data and posts it to the ERP.",
        "gpt-4o-mini", "Temporal workflow", 900,
        [_t("ocr_document", ["doc_id"], 1500, (300, 900)), _t("extract_fields", ["doc_id", "schema"], 400, (60, 200)),
         _t("validate_vendor", ["vendor_id"], 150, (20, 60)), _t("post_to_erp", ["payload"], 350, (15, 40))],
        [["ocr_document", "extract_fields", "validate_vendor", "post_to_erp"],
         ["ocr_document", "extract_fields", "extract_fields", "validate_vendor", "post_to_erp"]],
        ["lookup_po", "match_invoice", "approve_payment"],
        {"loop": 0.02, "tool_thrashing": 0.01, "hallucinated_tool": 0.01, "token_waste": 0.01},
        traffic_weight=1.3,
    ),
]

AGENT_BY_ID = {a.agent_id: a for a in AGENTS}
MAX_STEPS = 30


def _sentence(rng: random.Random, n: int, pool: Optional[List[str]] = None) -> str:
    pool = pool or WORD_BANK
    words = [rng.choice(pool) for _ in range(n)]
    for i in range(0, n, rng.randint(4, 7)):
        words.insert(i, str(rng.randint(10, 99999)))
    return " ".join(words)


def _arg_value(rng: random.Random, key: str) -> str:
    if key.endswith("_id"):
        return f"{key[:3].upper()}-{rng.randint(1000, 99999)}"
    if key in ("query", "question", "pattern"):
        return " ".join(rng.sample(WORD_BANK, rng.randint(2, 5)))
    if key == "url":
        return f"https://{rng.choice(WORD_BANK)}.example.org/{rng.choice(WORD_BANK)}/{rng.randint(1, 999)}"
    if key == "path":
        return f"src/{rng.choice(WORD_BANK)}/{rng.choice(WORD_BANK)}.py"
    if key == "sql":
        return f"SELECT {rng.choice(WORD_BANK)}, SUM({rng.choice(WORD_BANK)}) FROM {rng.choice(WORD_BANK)} GROUP BY 1"
    if key in ("amount", "nights"):
        return str(rng.randint(1, 900))
    if key in ("date", "checkin"):
        return f"2026-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"
    return " ".join(rng.sample(WORD_BANK, 2))


class _Builder:
    """Accumulates steps while tracking context size, so tokens grow realistically."""

    def __init__(self, rng: random.Random, agent: AgentProfile, t0: float):
        self.rng = rng
        self.agent = agent
        self.steps: List[Step] = []
        self.context = agent.base_prompt_tokens
        self.t = t0

    def _push(self, step: Step, context_added: int) -> None:
        step.timestamp = self.t
        self.t += step.latency_ms / 1000.0 + self.rng.uniform(0.05, 0.6)
        self.steps.append(step)
        self.context += context_added + step.output_tokens

    def tool(self, name: str, args: Optional[Dict] = None, output: Optional[str] = None,
             status: str = "ok", known: bool = True) -> None:
        rng = self.rng
        spec = self.agent.tool(name) if known else ToolSpec(name, ["input"], 15, (10, 30))
        if args is None:
            args = {k: _arg_value(rng, k) for k in spec.arg_keys}
        out_toks = rng.randint(*spec.output_tokens)
        if output is None:
            output = _sentence(rng, max(6, out_toks // 12))
        if status == "error":
            out_toks = rng.randint(10, 40)
        latency = spec.latency_ms * rng.lognormvariate(0, 0.35)
        self._push(Step(
            index=len(self.steps), type="tool_call", tool_name=name, arguments=args,
            output=output, status=status, latency_ms=round(latency, 1),
            input_tokens=self.context, output_tokens=rng.randint(25, 110),
        ), out_toks)

    def llm(self, text: str, out_tokens: int) -> None:
        latency = 400 + out_tokens * self.rng.uniform(8, 18)
        self._push(Step(
            index=len(self.steps), type="llm", output=text, latency_ms=round(latency, 1),
            input_tokens=self.context, output_tokens=out_tokens,
        ), 0)

    def final(self, text: Optional[str] = None) -> None:
        rng = self.rng
        out = rng.randint(120, 450)
        text = text or _sentence(rng, rng.randint(25, 60))
        self._push(Step(
            index=len(self.steps), type="final_answer", output=text,
            latency_ms=round(500 + out * rng.uniform(8, 15), 1),
            input_tokens=self.context, output_tokens=out,
        ), 0)

    @property
    def full(self) -> bool:
        return len(self.steps) >= MAX_STEPS


def _healthy_body(b: _Builder, length_cap: Optional[int] = None) -> None:
    """Emit a healthy workflow, including benign patterns that look suspicious."""
    rng, agent = b.rng, b.agent
    plan = list(rng.choice(agent.workflows))
    if length_cap is not None:
        plan = plan[:length_cap]
    for name in plan:
        if b.full:
            return
        r = rng.random()
        if r < 0.08:
            # Transient error(s) then an identical retry that succeeds. Two
            # failures in a row produce an identical-call streak of 3.
            args = {k: _arg_value(rng, k) for k in agent.tool(name).arg_keys}
            for _ in range(rng.choice([1, 1, 2])):
                b.tool(name, dict(args), output="ERROR: upstream timeout, please retry", status="error")
            b.tool(name, dict(args))
            continue
        if 0.08 <= r < 0.12:
            # Polling a long-running job: identical calls return "pending"
            # until the job completes. Early on this is indistinguishable
            # from a loop; it resolves once real output arrives.
            args = {k: _arg_value(rng, k) for k in agent.tool(name).arg_keys}
            job = f"JOB-{rng.randint(1000, 9999)}"
            for _ in range(rng.randint(2, 4)):
                b.tool(name, dict(args), output=f"status pending for {job} retry later")
            b.tool(name, dict(args))
            continue
        if r < 0.16 and agent.paginated_tool == name:
            # Pagination: same tool, page arg changes, each page is new information.
            base = {k: _arg_value(rng, k) for k in agent.tool(name).arg_keys}
            for page in range(1, rng.randint(3, 5)):
                b.tool(name, {**base, "page": page})
            continue
        if r < 0.24 and agent.alternation_pair and name == agent.alternation_pair[0]:
            # Productive alternation, e.g. fetch -> extract on several sources.
            a, c = agent.alternation_pair
            for _ in range(rng.randint(2, 4)):
                b.tool(a)
                b.tool(c)
            continue
        if r < 0.28:
            b.llm(_sentence(rng, rng.randint(20, 50)), rng.randint(120, 420))
        elif r < 0.33:
            # Long but genuinely new reasoning (planning, analysis).
            b.llm(_sentence(rng, rng.randint(80, 160)), rng.randint(600, 1400))
        b.tool(name)


def _inject_loop(b: _Builder) -> None:
    rng, agent = b.rng, b.agent
    variant = rng.choices(["exact", "cycle", "rephrase"], [0.45, 0.25, 0.30])[0]
    subtle = rng.random() < 0.3
    reps = 3 if subtle else rng.randint(4, 9)
    if variant == "exact":
        name = rng.choice(agent.tool_names)
        args = {k: _arg_value(rng, k) for k in agent.tool(name).arg_keys}
        out = _sentence(rng, 18)
        for _ in range(reps):
            if b.full:
                break
            b.tool(name, dict(args), output=out)
            if rng.random() < 0.3:
                b.llm("The previous result was not sufficient, I will try again " + out[:60], rng.randint(60, 160))
    elif variant == "cycle":
        a, c = rng.sample(agent.tool_names, 2)
        oa, oc = _sentence(rng, 14), _sentence(rng, 14)
        args_a = {k: _arg_value(rng, k) for k in agent.tool(a).arg_keys}
        args_c = {k: _arg_value(rng, k) for k in agent.tool(c).arg_keys}
        for _ in range(reps):
            if b.full:
                break
            b.tool(a, dict(args_a), output=oa)
            b.tool(c, dict(args_c), output=oc)
    else:
        name = rng.choice(agent.tool_names)
        spec = agent.tool(name)
        base = {k: _arg_value(rng, k) for k in spec.arg_keys} or {"input": "status"}
        key = next(iter(base))
        out = _sentence(rng, 16)
        suffixes = ["", " again", " latest", " updated", " please", " v2", " now", " full", " exact"]
        for i in range(reps):
            if b.full:
                break
            args = dict(base)
            args[key] = f"{base[key]}{suffixes[i % len(suffixes)]}"
            jitter = " ".join(rng.sample(out.split(), 3))
            b.tool(name, args, output=f"{out} {jitter}")
    if subtle:
        _healthy_body(b, length_cap=2)
        if not b.full:
            b.final()
    elif not b.full and rng.random() < 0.5:
        b.final("I was unable to obtain a definitive result. " + _sentence(rng, 10))


def _inject_thrashing(b: _Builder) -> None:
    rng, agent = b.rng, b.agent
    n = rng.randint(5, 14)
    err_p = rng.uniform(0.3, 0.75)
    last = None
    junk = ["no results", "ERROR: invalid arguments", "ERROR: missing required field", "empty response",
            "ERROR: schema mismatch", "nothing found for input"]
    for _ in range(n):
        if b.full:
            break
        name = rng.choice([t for t in agent.tool_names if t != last])
        last = name
        bad = rng.random() < err_p
        spec = agent.tool(name)
        args = {k: rng.choice(["", "?", "null", _arg_value(rng, k)]) for k in spec.arg_keys}
        msg = rng.choice(junk)
        b.tool(name, args, output=msg, status="error" if bad and msg.startswith("ERROR") else "ok")
        if rng.random() < 0.2:
            b.llm("Let me try a different approach to " + rng.choice(WORD_BANK), rng.randint(60, 200))
    if not b.full and rng.random() < 0.6:
        b.final("Partial answer based on limited information. " + _sentence(rng, 8))


def _inject_hallucination(b: _Builder) -> None:
    rng, agent = b.rng, b.agent
    count = rng.choices([1, 2, 3, 4], [0.35, 0.3, 0.2, 0.15])[0]
    for _ in range(count):
        if b.full:
            break
        fake = rng.choice(agent.fake_tools)
        b.tool(fake, {"input": _arg_value(rng, "query")},
               output=f"ERROR: tool '{fake}' is not registered for this agent", status="error", known=False)
        if rng.random() < 0.4:
            b.llm(f"I will use {fake} to get the information", rng.randint(50, 150))
    if rng.random() < 0.5:
        _healthy_body(b, length_cap=2)
    if not b.full:
        b.final()


def _restate(rng: random.Random, pool: List[str], n_words: int) -> str:
    """Re-emit contiguous phrases from earlier output, as a rambling model does."""
    out: List[str] = []
    while len(out) < n_words:
        start = rng.randrange(max(1, len(pool) - 8))
        out.extend(pool[start:start + rng.randint(4, 12)])
    return " ".join(out[:n_words])


def _inject_token_waste(b: _Builder) -> None:
    rng = b.rng
    so_far = " ".join(s.output for s in b.steps) or _sentence(rng, 40)
    pool = so_far.split()
    subtle = rng.random() < 0.3
    for _ in range(rng.randint(2, 3) if subtle else rng.randint(3, 7)):
        if b.full:
            break
        n_words = rng.randint(80, 200)
        restated = _restate(rng, pool, n_words)
        if subtle:
            restated += " " + _sentence(rng, n_words // 4)
        b.llm("Let me carefully reconsider everything so far. " + restated,
              rng.randint(500, 1200) if subtle else rng.randint(700, 2600))
        if rng.random() < 0.3:
            b.tool(rng.choice(b.agent.tool_names))
    if not b.full and rng.random() < 0.5:
        b.final("In summary, " + _restate(rng, pool, 40))


INJECTORS = {
    "loop": _inject_loop,
    "tool_thrashing": _inject_thrashing,
    "hallucinated_tool": _inject_hallucination,
    "token_waste": _inject_token_waste,
}


def _long_productive(b: _Builder) -> None:
    """Hard negative: a long, expensive but genuinely productive run."""
    rng, agent = b.rng, b.agent
    for _ in range(rng.randint(9, 16)):
        if b.full:
            break
        b.tool(rng.choice(agent.tool_names))
        if rng.random() < 0.3:
            b.llm(_sentence(rng, rng.randint(40, 90)), rng.randint(300, 700))


TASK_TEMPLATES = {
    "support-bot": ["Customer asks about refund for order {id}", "Where is my package {id}?", "Cancel subscription for {id}"],
    "research-agent": ["Summarize recent findings on {w}", "Compare {w} and {w2} approaches", "Find sources about {w}"],
    "code-assistant": ["Fix failing test in {w} module", "Add {w} parameter to {w2} function", "Refactor {w} config loading"],
    "data-analyst": ["Quarterly {w} by region", "Why did {w} drop last month?", "Build {w} cohort report"],
    "travel-planner": ["Plan 4 days in {w} city", "Find flights and hotel for {w} trip", "Weekend itinerary under budget"],
    "invoice-processor": ["Process invoice {id}", "Validate vendor on invoice {id}", "Post invoice {id} to ERP"],
}


def generate_run(
    rng: random.Random,
    agent: Optional[AgentProfile] = None,
    label: Optional[str] = None,
    t0: Optional[float] = None,
    failure_scale: float = 1.0,
) -> Run:
    agent = agent or rng.choices(AGENTS, [a.traffic_weight for a in AGENTS])[0]
    if label is None:
        roll, acc = rng.random(), 0.0
        label = "healthy"
        for ft, p in agent.failure_rates.items():
            acc += p * failure_scale
            if roll < acc:
                label = ft
                break

    b = _Builder(rng, agent, t0 if t0 is not None else 0.0)
    onset: Optional[int] = None
    if label == "healthy":
        if rng.random() < 0.08:
            _long_productive(b)
        else:
            _healthy_body(b)
        if not b.full:
            b.final()
    else:
        prefix_len = rng.randint(0, 3)
        if prefix_len:
            _healthy_body(b, length_cap=prefix_len)
        onset = len(b.steps)
        INJECTORS[label](b)

    tmpl = rng.choice(TASK_TEMPLATES[agent.agent_id])
    task = tmpl.format(id=rng.randint(10000, 99999), w=rng.choice(WORD_BANK), w2=rng.choice(WORD_BANK))
    return Run(
        run_id=str(uuid.UUID(int=rng.getrandbits(128))),
        agent_id=agent.agent_id,
        steps=b.steps,
        task=task,
        model=agent.model,
        registered_tools=agent.tool_names,
        source_label=label,
        failure_onset=onset,
    )


def generate_dataset(n: int, seed: int = 7, failure_scale: float = 1.0, balanced: bool = False) -> List[Run]:
    """`balanced=True` over-samples failures so every class has enough examples to learn from."""
    rng = random.Random(seed)
    runs: List[Run] = []
    for i in range(n):
        label = None
        if balanced:
            label = rng.choices(["healthy", "loop", "tool_thrashing", "hallucinated_tool", "token_waste"],
                                [0.5, 0.125, 0.125, 0.125, 0.125])[0]
        runs.append(generate_run(rng, label=label, failure_scale=failure_scale))
    return runs


# --------------------------------------------------------------------------
# Outcome model for simulated intervention feedback
# --------------------------------------------------------------------------

# P(run ultimately succeeds | true condition, intervention)
SUCCESS_PROB = {
    "healthy":           {"continue": 0.95, "reflect": 0.92, "retry_step": 0.90, "escalate_model": 0.95, "human_review": 0.95, "terminate": 0.0},
    "loop":              {"continue": 0.05, "reflect": 0.75, "retry_step": 0.30, "escalate_model": 0.60, "human_review": 0.85, "terminate": 0.0},
    "tool_thrashing":    {"continue": 0.05, "reflect": 0.35, "retry_step": 0.15, "escalate_model": 0.78, "human_review": 0.85, "terminate": 0.0},
    "hallucinated_tool": {"continue": 0.10, "reflect": 0.55, "retry_step": 0.78, "escalate_model": 0.70, "human_review": 0.85, "terminate": 0.0},
    "token_waste":       {"continue": 0.30, "reflect": 0.45, "retry_step": 0.20, "escalate_model": 0.40, "human_review": 0.70, "terminate": 0.0},
}


def simulate_outcome(rng: np.random.Generator, true_label: str, action: str) -> bool:
    return bool(rng.random() < SUCCESS_PROB[true_label][action])


def expected_reward(true_label: str, action: str) -> float:
    from .bandit import compute_reward
    p = SUCCESS_PROB[true_label][action]
    return p * compute_reward(True, action, true_label) + (1 - p) * compute_reward(False, action, true_label)
