# Agent Observability System

**Real-time monitoring and intervention for LLMs and LLM agents**

Two things in one workspace-based, multi-user dashboard:

- **LLM monitoring** — route your apps' OpenAI (ChatGPT models), Anthropic (Claude) and Google
  (Gemini) calls through a gateway by changing one base URL. Every call is logged and checked
  against *prompt contracts* (your rules); violations raise alerts and can be **blocked or
  auto-repaired** before they reach users. Scheduled drift tests catch silent provider changes.
- **Agent monitoring** — detects silent failures in LLM agents **while they happen** — infinite loops, tool thrashing,
hallucinated tool calls and token waste — and recommends an intervention (reflect, retry,
escalate, ask a human, or stop) that is learned from real outcomes.

Traditional monitoring sees a 200 OK and normal latency. This system looks at the *behavior*
of each run, step by step.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Node 18+](https://img.shields.io/badge/node-18+-green.svg)](https://nodejs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115.0-009688.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18-61DAFB.svg)](https://reactjs.org/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

```mermaid
flowchart LR
    A[Agent step<br/>via SDK] --> F[Behavioral<br/>features]
    F --> R[Rule detectors]
    F --> U[Unsupervised<br/>IsolationForest + k-NN<br/>HDBSCAN]
    F --> S[Supervised<br/>gradient boosting<br/>on run prefixes]
    R -. stacked .-> S
    U -. stacked .-> S
    R --> X[Fusion +<br/>open-set gate]
    U --> X
    S --> X
    X --> K[Risk, failure type,<br/>evidence]
    K --> P[LinUCB policy<br/>+ guardrails]
    P --> I[Intervention<br/>returned to agent]
    K --> D[Dashboard]
    D --> H[Human review]
    H -- outcome = reward --> P
    H -- label --> S
```

## Key Features

- **LLM Gateway** - OpenAI, Claude and Gemini through their official SDKs, streaming included, no code changes beyond the base URL
- **Prompt Contracts** - Format, schema, length, forbidden content, PII, refusals, relevance and LLM-judge rules per project
- **Enforcement** - Monitor, block (HTTP 422) or repair (re-ask the model, then fall back to another model)
- **Alerts** - Per-call (PII leak, prompt injection, blocked) and windowed (violation rate, errors, latency, cost) via in-app, Slack, webhook, email
- **Drift Tests** - Fixed prompts on a schedule, compared with a baseline, to catch provider-side model changes
- **Accounts & Workspaces** - Email/password and Google sign-in, roles (admin/member/viewer), per-workspace API keys, provider keys encrypted at rest
- **Real-time Detection** - Catches failures as they happen, not after
- **Multi-Layer ML** - Rules + Unsupervised + Supervised models working together
- **Early Alerts** - Flags 74% of failing real agent runs within 2 steps of onset
- **Smart Interventions** - RL policy learns which actions work best
- **Rich Dashboard** - Full observability with graphs, heatmaps, and flow diagrams
- **Continuous Learning** - Gets smarter from human feedback
- **Cost Savings** - Flags failing runs early enough to avoid 71% of their tokens (on real traces)
- **Fail-Safe Design** - Agents keep running even if monitoring is down
- **Easy Integration** - Simple Python SDK with no heavy dependencies
- **Production Ready** - Docker support, PostgreSQL/SQLite, comprehensive tests

## What Problems Does It Solve?

| Problem | Detection Method | Intervention |
|---------|------------------|--------------|
| **Infinite Loops** | Identical tool call streaks | Reflect with hint to try different approach |
| **Tool Thrashing** | Rapid switching without progress | Retry with stronger model |
| **Hallucinated Tools** | Calls to non-existent tools | Stop or escalate to human |
| **Token Waste** | High spend without new information | Stop to cap costs |
| **Repeated Errors** | Error streaks and patterns | Human review or alternative strategy |
| **Stuck Agents** | Novelty drops, no progress | Reflect or escalate |

## How it works

Every agent step (tool call, reasoning step, or final answer) is sent to the API. After each
step the run is re-scored by three learning paradigms that cover each other's blind spots:

| Layer | Method | Why it is there |
|---|---|---|
| **Rules** | Deterministic detectors for identical-call streaks, tool cycles, near-duplicate rephrasing, switching-without-progress, unregistered tools, spend-without-progress | Exact, explainable evidence pointing at specific steps. Unregistered-tool calls set a hard risk floor. |
| **Unsupervised** | IsolationForest + k-NN distance, calibrated to percentiles of normal traffic; HDBSCAN behavioral archetypes; PCA behavior map | Needs no labels; flags behavior unlike anything normal, including failure modes nobody has named yet. |
| **Supervised** | Gradient-boosted trees over behavioral features + rule outputs + novelty (stacked), trained on **run prefixes** | Names the failure type and recognizes it 1–2 steps after onset. Retrains from human labels. |
| **Fusion** | Logistic regression fit on validation data, plus an **open-set gate** (rule ≥ r AND novelty ≥ n) | Learned signal weights; the gate keeps detecting failure types the classifier never saw. |
| **Policy (RL)** | LinUCB contextual bandit with guardrails, warm-started offline, updated on every review | Learns which intervention works for which failure profile. State is persisted after every update. |

Human review closes both loops: the **outcome** rewards the policy immediately, and the **label**
retrains the classifier (manually or automatically every N labels). New model versions are
promoted only if they are not worse on the held-out set. The review queue is ordered by
classifier uncertainty (active learning), so each label is as informative as possible.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the design rationale and data model.

## Results (real agent runs)

Trained and evaluated on real agent runs: [SWE-agent trajectories](https://huggingface.co/datasets/nebius/SWE-agent-trajectories)
(CC BY 4.0), Llama-based SWE-agent models trying to resolve real GitHub issues. Two shards, ~13,000 runs,
7,508 of them labeled. The split is by GitHub issue, so no test run shares an issue with training.

Labels come from what actually happened in each run (`ml/real_traces.py`), with the step where it started:

| Label | What happened in the run |
|---|---|
| Hallucinated tool | the agent ran a command that does not exist (the environment answered "command not found") |
| Loop | the same command, with the same output, three times in a row |
| Tool thrashing | 10+ navigation/search commands across 4+ tools with no edit or execution, in a failed run |
| Token waste | the run exhausted its context/cost budget without resolving the issue |
| Healthy | the issue was resolved and none of the above happened |

These are behavioral labels, not human judgments; labels from the review queue are added on top
(weighted higher) and retrain the model on your own agents.

Measured on 1,500 held-out real runs (62% failing):

| | Precision | Recall | Macro-F1 (5 classes) | Healthy runs ever flagged | Caught ≤ 2 steps after onset | Avoidable tokens flagged |
|---|---|---|---|---|---|---|
| Fused engine (v1) | 91.3% | 96.5% | 0.73 | 21% | 74% | 71% of failing-run tokens |

Per class (F1): healthy 0.89, loop 0.77, token waste 0.72, tool thrashing 0.67, hallucinated tool 0.60.

**Each paradigm alone vs fused** (recall at 5% FPR): rules 64%, unsupervised 76%, supervised 73%, **fused 77%**
(PR-AUC 0.90 / 0.96 / 0.97 / **0.97**).

**A failure type never seen in training** (leave-one-type-out):

| Held-out type | Rules only | Unsupervised only | Supervised only | **Fused** |
|---|---|---|---|---|
| Loop | 100% @ 64% FPR | 100% @ 30% FPR | 86% @ 13% FPR | **88% @ 15% FPR** |
| Tool thrashing | 82% @ 64% | 95% @ 34% | 62% @ 6% | **64% @ 7%** |
| Hallucinated tool | 98% @ 64% | 90% @ 28% | 75% @ 10% | **78% @ 12%** |
| Token waste | 94% @ 64% | 98% @ 32% | 82% @ 13% | **93% @ 17%** |

Real agents are noisy: false-positive rates are far higher than on simulated data, and rules alone
flag most healthy runs. Fusion keeps most of the recall at a fraction of the false positives.

**Intervention policy.** No public dataset records what happened *after* an intervention, so the
policy starts from zero: it follows a failure-type playbook (loop → retry the step, tool thrashing
→ human review, hallucinated tool → stronger model, token waste → stop) until it has learned from
20 reviewed outcomes, then the LinUCB bandit takes over and keeps learning from every review.

All of these numbers are regenerated by `python -m scripts.bootstrap` and shown on the
dashboard's **Detection models** and **Intervention policy** pages.

## Quick Start

### Prerequisites
- Python 3.10+
- Node.js 18+
- Docker & Docker Compose (optional)

### Option 1: Local Development (Recommended for Testing)

**Backend Setup:**
```bash
cd backend

# Install dependencies
pip install -r requirements.txt

# Download the real agent traces (~184 MB, once), then train on them (~10 minutes)
python -m scripts.fetch_real_traces
python -m scripts.bootstrap                     # add --import-runs 400 to show held-out real runs on the dashboard

# Start API server
uvicorn app.main:app --reload --port 8000
```

**Frontend Setup (in a new terminal):**
```bash
cd frontend

# Install dependencies
npm install

# Create environment file
cp .env.example .env

# Start dev server
npm run dev
```

**Access the application:**
- Dashboard: http://localhost:5173 → **Create an account**. The first account becomes admin of the
  *Main workspace*; later sign-ups get their own workspace. Dashboards fill with your own traffic (gateway,
  browser extension, SDK). Nothing is simulated.
- API Docs: http://localhost:8000/docs
- Health Check: http://localhost:8000/health

**Stream Live Traffic (optional):**
```bash
# Replay held-out real agent runs step by step, as if live
python sdk/examples/live_traffic.py --runs 30
```

**Google sign-in (optional):** create an OAuth client (type *Web application*) in Google Cloud
Console with the authorized redirect URI `http://localhost:5173/api/auth/google/callback`, then set
in `backend/.env`:

```bash
AOBS_GOOGLE_CLIENT_ID=...apps.googleusercontent.com
AOBS_GOOGLE_CLIENT_SECRET=...
AOBS_PUBLIC_URL=http://localhost:5173
```

The "Continue with Google" button appears once both are set.

### Option 2: Docker Compose (Production-like Setup)

```bash
# Generate the key that encrypts stored provider API keys (keep it safe; losing it makes stored keys unreadable)
export AOBS_SECRET_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")

# Start all services (PostgreSQL + API + Dashboard)
docker compose up --build

# Access dashboard at http://localhost:8080
```

First startup trains models and seeds demo data (takes ~2-3 minutes).

## Monitoring your LLMs (OpenAI, Claude, Gemini)

1. **Settings → Provider keys**: add your OpenAI / Anthropic / Gemini API keys. They are encrypted
   at rest (Fernet: AES-128 + HMAC, key `AOBS_SECRET_KEY`) and never sent back to the browser.
2. **Settings → API keys**: create a workspace key (`aobs_…`). Your apps use it in place of the provider key.
3. Point your SDK at the gateway (the **Connect LLMs** page has copy-paste snippets):

```python
from openai import OpenAI
client = OpenAI(base_url="http://127.0.0.1:8000/gateway/openai/v1", api_key="aobs_...",
                default_headers={"X-AOBS-Project": "support-assistant"})   # optional: apply a contract

import anthropic
claude = anthropic.Anthropic(base_url="http://127.0.0.1:8000/gateway/anthropic", api_key="aobs_...")

from google import genai
from google.genai import types
gemini = genai.Client(api_key="aobs_...", http_options=types.HttpOptions(base_url="http://127.0.0.1:8000/gateway/gemini"))
```

Requests and responses (including streams) are forwarded unchanged; the gateway observes them.
Optional headers, stripped before forwarding: `X-AOBS-Project` (contract), `X-AOBS-Session`
(conversation id), `X-AOBS-User`, `X-AOBS-Tags`, `X-AOBS-Credential` (non-default stored key).

**Prompt contracts** (dashboard → Prompt contracts) define what a project's responses must do:

| Rule | Checks |
|---|---|
| Valid JSON / JSON schema | Structured output, including fenced code blocks |
| Max/min words, max characters | Length limits |
| Must / must not match pattern, must / must not mention | Required or forbidden content |
| Writing system | Response is in the expected script (Latin, Cyrillic, CJK, …) |
| No personal data | Emails, phone numbers, Luhn-valid card numbers, SSNs |
| Does not refuse, stays on topic | Refusals; lexical relevance to the prompt |
| LLM judge | Any plain-language rule, evaluated by a judge model you choose |

Built-in checks run on every call: PII in the response, prompt-injection attempts in the input,
refusals, truncation, empty responses and provider errors.

Each contract has a **mode**: *monitor* (log and alert, zero added latency), *block* (a critical
violation returns HTTP 422 `aobs_policy_violation`), or *repair* (the model is shown the violations
and asked to fix its answer, then fallback models are tried, then the response is blocked).

**Alerts** fire per call or on windowed metrics (violation rate, error rate, p95 latency, judge
score, adherence, cost), resolve automatically when the condition clears, and deliver in-app,
to Slack, to a webhook, or by email (SMTP). **Drift tests** run a fixed prompt on a schedule at
temperature 0 and alert when the answer stops matching its baseline or breaks its contract.

**Chat websites** (gemini.google.com, chatgpt.com, claude.ai) don't go through the gateway. For those,
install the [Chat Monitor browser extension](browser-extension/README.md): it sends each finished answer
to `/api/llm/ingest/browser-turn` for the same checks and shows the result under the answer
(monitoring only; mobile and desktop chat apps are not covered).

## Instrumenting your agent

The SDK (`sdk/agent_observability`) has no dependencies. Register the agent's tools once so
hallucinated tool calls are detected exactly, then stream steps:

```python
from agent_observability import ObservabilityClient

client = ObservabilityClient("http://127.0.0.1:8000", api_key="aobs_...")  # workspace key (Settings → API keys)
client.register_agent("support-bot", tools=["search_kb", "get_order", "send_reply"], model="gpt-4o-mini")

with client.run("support-bot", task=user_message) as run:
    for _ in range(MAX_STEPS):
        tool, args = llm.decide(messages)
        result = tools[tool](**args)
        verdict = run.tool_call(tool, args, output=result,
                                input_tokens=usage.input_tokens, output_tokens=usage.output_tokens)
        if verdict and verdict.should_stop:          # terminate / human_review
            break
        if verdict and verdict.correction_prompt:    # reflect / retry_step / escalate_model
            messages.append({"role": "user", "content": verdict.correction_prompt})
    run.final_answer(answer)

# Later, once the outcome is known (closes the learning loop):
client.feedback(run.run_id, label="healthy", resolved=True)
```

`correction_prompt` is written from the detector evidence, e.g. *"You are repeating the same
actions without making progress. - search_kb called 4 times with identical arguments (steps 6–9).
Do not repeat a tool call with the same arguments…"*. The run page shows the same text.

The client fails open: if the service is unreachable, the agent keeps running.
In development, `dev-local-key` also works and maps to the Main workspace (disabled when
`AOBS_ENVIRONMENT=production` and in Docker Compose).

## Detection and correction

Detection runs on every call and every agent step; correction depends on what failed:

| Where | Detected | Corrected by |
|---|---|---|
| LLM gateway, `block`/`repair` contracts | Personal data in the answer (`no_pii`) | Masking it in the provider's own response format, streamed or not; no extra model call |
| | JSON wrapped in prose or a code fence (`json_valid`, `json_schema`) | Extracting the JSON value |
| | Any other critical rule | `repair`: the model is asked to fix its answer, then fallback models; else blocked (HTTP 422) |
| Any LLM call | Unusual output length, latency or relevance *for that model* (robust z-score vs. the model's last 500 calls) | Reported as "Unusual for this model" |
| Agent runs | Loops, tool thrashing, hallucinated tools, token waste, novel anomalies | A correction prompt for `reflect` / `retry_step` / `escalate_model`; `terminate` / `human_review` stop the run |

A deterministic correction is only used if the corrected text passes every critical rule when
checked again; the call log shows "Auto-corrected" with the fixes applied. Both corrections can be
switched off per contract. Reviewers can mark any call's flags as right, a false alarm, or a missed
problem; Prompt contracts then shows each check's measured precision.

## Plans and subscriptions

Every workspace has a plan. New workspaces start on Free; the demo workspace (and any workspace a
platform admin assigns) is on the unlimited internal plan.

| | Free | Pro ($5/mo) |
|---|---|---|
| Tracked LLM calls / month | 5,000 | 50,000 |
| Agent runs / month | 1,000 | 20,000 |
| Members | 2 | 5 |
| Prompt contracts / alert rules / drift tests | 2 / 3 / 1 | 10 / 20 / 5 |
| Content retention | 7 days | 30 days |
| LLM judge; block, repair and auto-correct | – | ✓ |
| Slack, webhook and email alerts | in-app only | ✓ |

Pro has a one-time 14-day free trial. Limits never break a customer's app: over the monthly
quota or the per-minute rate limit, the gateway still forwards every request and only skips
analysis (response header `x-aobs-analysis: skipped-quota`), and the workspace gets one in-app
alert. Analysis-only endpoints (agent ingest, browser extension) return 402 / 429, and the SDK and
extension fail open. Downgrades keep existing configuration: a block contract on a plan without
enforcement simply runs as monitor.

**Billing.** With Stripe configured (`AOBS_STRIPE_*`), admins upgrade through Stripe Checkout and
manage or cancel in the Stripe customer portal; webhooks keep the plan in sync (signature-verified,
idempotent). Without Stripe, a platform admin sets plans in the admin console.

**Platform admin.** Emails in `AOBS_PLATFORM_ADMINS` see `/admin`: every workspace with its plan,
status and this month's usage (metadata only, never prompts or responses), and can change plans.

**Live updates.** The dashboard keeps a server-sent-events connection (`/api/stream`); new calls,
alerts and flagged runs appear without refreshing, and critical ones raise a notification.

## API

Interactive docs at `http://127.0.0.1:8000/docs`. `/api` routes accept a signed-in dashboard
session (cookie) or a workspace API key (`X-API-Key` or `Authorization: Bearer aobs_…`), and every
result is scoped to that workspace. Viewers are read-only.

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/auth/signup`, `/api/auth/login`, `/api/auth/logout` | Email/password accounts |
| GET | `/api/auth/google/login` | Google sign-in (OAuth authorization-code flow) |
| GET/POST | `/api/workspace/members`, `/api/workspace/api-keys`, `/api/workspace/credentials` | Members, API keys, encrypted provider keys |
| POST | `/gateway/{openai,anthropic,gemini}/...` | LLM gateway (provider-native request/response formats) |
| GET | `/api/llm/overview`, `/api/llm/calls`, `/api/llm/calls/{id}` | Adherence dashboard and call log |
| CRUD | `/api/llm/contracts`, `/api/llm/alert-rules`, `/api/llm/drift-tests` | Contracts, alert rules, drift tests |
| GET/PATCH | `/api/llm/alerts` | Alert events (acknowledge / resolve) |
| POST | `/api/ingest/runs/start` | Open a live run |
| POST | `/api/ingest/runs/{id}/steps` | Append a step; returns risk, failure type, evidence, recommended action |
| POST | `/api/ingest/runs/{id}/finish` | Close a live run |
| POST | `/api/ingest/runs`, `/api/ingest/runs/batch` | Ingest completed runs (post-hoc) |
| POST | `/api/runs/{id}/feedback` | Report the true condition and outcome → policy reward + training label |
| POST | `/api/agents` | Register an agent and its tools |
| GET | `/api/overview`, `/api/runs`, `/api/runs/{id}` | Dashboard data |
| GET | `/api/agents`, `/api/agents/{id}`, `/api/agents/compare` | Per-agent stats, tool-flow graph, comparison |
| GET | `/api/review-queue` | Flagged runs awaiting review (sorted by uncertainty) |
| GET | `/api/models`, `/api/models/{v}/metrics`, `/api/behavior-map` | Model registry and evaluation |
| POST | `/api/models/retrain` | Retrain with collected labels (background) |
| GET | `/api/policy` | Policy state, learning curves, live rewards |
| GET | `/api/plans` | Public plan catalog |
| GET/POST | `/api/billing`, `/api/billing/trial`, `/api/billing/checkout`, `/api/billing/portal` | Plan, usage, trial, Stripe Checkout / portal |
| POST | `/api/billing/webhook` | Stripe webhook (signature-verified) |
| GET/PATCH | `/api/admin/overview`, `/api/admin/workspaces/{id}` | Platform admin console |
| GET | `/api/stream` | Live updates (server-sent events: `call`, `alert`, `run`) |
| POST | `/api/llm/calls/{id}/feedback` | Reviewer verdict on a call's flags |
| GET | `/api/llm/check-quality` | Measured precision of each check |
| GET | `/health/ready` | Readiness (database reachable, models loaded) |

## Dashboard Features

Built with React, TanStack Query (cached, auto-refreshing data), Radix UI (accessible menus, dialogs, tooltips), cmdk (command palette), Lucide icons, Sonner toasts and Recharts.

- **Ctrl/⌘ + K** opens a command palette: jump to any page, paste a call or run ID, or search calls and runs.
- Light, dark or system theme (account menu), and a collapsible sidebar; both are remembered per browser.
- **Settings → About & how tracking works** explains each stage a message goes through, lets you trace a sample message (with the triggering words highlighted), and shows the real trace of your most recent message.

### LLM monitoring
- **Overview** - calls by outcome, violation rate, adherence per model, most-violated checks, spend, latency
- **Live calls** - auto-refreshing call log with filters; detail shows prompt, response, every check and its reason, enforcement attempts
- **Prompt contracts** - rule builder, monitor/block/repair modes, fallback models, dry-run tester
- **Alerts** - open/acknowledged/resolved events and rule management with test notifications
- **Drift tests** - scheduled baseline comparisons with a similarity trend
- **Connect LLMs** - setup status and SDK snippets (Python, JavaScript, LangChain, curl)
- **Settings** - workspace, members and roles, API keys, provider keys, privacy (content storage, PII masking, retention), LLM judge

### Overview Page
- **Real-time KPIs**: Run volume, flagged issues, critical problems
- **Cost Analysis**: Total token spend vs. avoidable waste
- **Failure Distribution**: Visual breakdown of failure types
- **Agent Health**: Per-agent reliability scores
- **Recent Alerts**: Latest flagged runs

### Runs & Run Detail
- Browse all agent executions with filtering
- **Step-by-step risk evolution** as the run progresses
- Token usage and cost per step
- Rule evidence with specific step indexes
- Class probabilities from the ML model
- Policy's per-action confidence scores
- Full trace with timing information
- **Review form** for human feedback

### Agents & Comparison
- Reliability and cost metrics per agent
- **Tool flow graph** - visualize how runs navigate between tools (loops stand out!)
- Side-by-side agent comparison

### Review Queue
- **Active learning queue** - ordered by classifier uncertainty
- Most informative cases first
- Retrain controls

### Detection Models
- Pipeline architecture diagram
- **Model version history** (v1, v2, ...)
- Paradigm comparison (rules vs unsupervised vs supervised)
- Leave-one-failure-type-out study results
- Precision-Recall curves and confusion matrices
- **Early detection histogram** - steps from onset to alert
- Feature importance rankings
- **Behavior map** - PCA projection of run embeddings

### Intervention Policy
- **Warm-start learning curves** vs baselines
- What the policy learned per failure type
- Live reward tracking
- Learned weights per action

## Project Structure

```
backend/
  ml/              # ML pipeline
    schema.py      # Data models
    features.py    # 29 behavioral features
    detectors.py   # Rule-based detectors
    models.py      # Unsupervised models (IsolationForest, k-NN, HDBSCAN)
    engine.py      # Fusion engine + supervised classifier
    bandit.py      # LinUCB intervention policy
    real_traces.py # Real SWE-agent runs -> training data and labels
    simulator.py   # Synthetic runs for unit tests only
    training.py    # Training and evaluation
  app/             # FastAPI application
    main.py        # App startup, routers, background worker
    config.py      # Configuration management
    db.py          # Database connection
    orm.py         # Accounts, workspaces, credentials, agent-monitoring tables
    orm_llm.py     # LLM calls, contracts, alerts, drift tests
    auth.py        # Sessions, API keys, roles, CSRF protection
    crypto.py      # Encryption of stored provider keys
    routes.py      # Agent-monitoring endpoints
    routes_account.py  # Sign-up/login, Google, workspaces, members, keys
    routes_llm.py  # LLM monitoring endpoints
    pricing.py     # Token cost estimation
    llm/           # LLM monitoring
      gateway.py   # Observing/enforcing proxy for OpenAI, Anthropic, Gemini
      providers.py # Provider wire formats (requests, responses, streams)
      checks.py    # Deterministic rules and built-in checks
      judge.py     # LLM-as-judge
      evaluator.py # Combines checks into a verdict
      alerts.py    # Alert rules, events, Slack/webhook/email delivery
      drift.py     # Scheduled drift tests
      worker.py    # Background loop: window alerts, drift tests, retention
      demo.py      # Simulated LLM traffic for the demo workspace
    services/      # Business logic
      ingest.py    # Real-time ingestion
      analytics.py # Dashboard queries
      registry.py  # Model versioning
      training.py  # Retrain orchestration
  scripts/
    bootstrap.py   # Setup: train on real traces
    fetch_real_traces.py  # Download the real traces
  tests/           # 54 tests: ML, auth, gateway (incl. the real OpenAI SDK), checks, API
  data/            # SQLite database (generated)
  artifacts/       # Trained models (generated)

frontend/          # React + Vite dashboard
  src/
    pages/         # Overview, Runs, Agents, Models, Policy, Review
    components/    # Reusable UI: Heatmap, ToolFlowGraph, PipelineDiagram
    api.js         # API client
    theme.js       # Design tokens

sdk/              # Python client library
  agent_observability/
    client.py      # ObservabilityClient
  examples/
    live_traffic.py  # Simulated agent with interventions

docs/
  ARCHITECTURE.md  # Design decisions and data model
```

## Testing

Run the comprehensive test suite:

```bash
cd backend

# Install dev dependencies
pip install -r requirements-dev.txt

# Run all tests with coverage
pytest

# Run with verbose output
pytest -v

# Generate HTML coverage report  
pytest --cov-report=html
```

**Test Coverage**: 54 tests covering features, detectors, policy, engine quality, API endpoints,
authentication and workspace isolation, the LLM gateway (all three providers, streaming,
block/repair/fallback, judge, alerts, drift tests) against a mock provider, and the checks.

## Troubleshooting

### Backend Issues

**ModuleNotFoundError or import errors:**
```bash
cd backend
pip install -r requirements.txt
```

**"A model already exists" error:**
```bash
python -m scripts.bootstrap --reset
```

**Database locked (SQLite):**
```bash
# Stop all backend processes first
rm data/observability.db*
python -m scripts.bootstrap
```

### Frontend Issues

**CORS errors in browser console:**
```bash
# Set in backend/.env:
AOBS_CORS_ORIGINS=http://localhost:5173,http://localhost:5174
```

**Redirected to the sign-in page / 401 errors:** the dashboard uses a session cookie; sign in
again. Leave `VITE_API_BASE` unset in `frontend/.env` during development so requests go through
the dev server's proxy (same origin, no CORS).

**"Cannot reach the API" / Failed to fetch:** the API is down or restarting. On Windows, a long-running
`uvicorn --reload` can stop accepting connections after many reloads; stop it and start it again.

**Gateway returns `aobs_missing_provider_key`:** add the provider's key under Settings → Provider keys.
**`aobs_auth_error`:** use a workspace key (`aobs_…`) as the SDK's api_key, not the provider key.

**After upgrading to the workspace version:** the schema changed; run `python -m scripts.bootstrap --reset`
(this deletes all data, including accounts).

### Docker Issues

**Docker daemon not running:**
- Windows/Mac: Start Docker Desktop
- Linux: `sudo systemctl start docker`

**Port already in use:**
```bash
# Windows:
netstat -ano | findstr :8000
# Linux/Mac:
lsof -i :8000
```

**Empty dashboard after install:**
```bash
# Dashboards show only real traffic. Connect an app (Connect LLMs page), or replay real agent runs:
cd backend
python -m scripts.bootstrap --reset --import-runs 400
python ../sdk/examples/live_traffic.py --runs 50
```

## Configuration

Environment variables (or `backend/.env`, see `backend/.env.example`):

| Variable | Default | |
|---|---|---|
| `AOBS_DATABASE_URL` | SQLite in `backend/data/` | e.g. `postgresql://user:pass@host/db` |
| `AOBS_ENVIRONMENT` | `development` | `production` disables the dev key, requires `AOBS_SECRET_KEY`, https-only public webhooks |
| `AOBS_SECRET_KEY` | generated in `backend/data/secret.key` (dev) | Fernet key encrypting provider keys; comma-separate to rotate |
| `AOBS_COOKIE_SECURE` | `false` | Set `true` behind HTTPS |
| `AOBS_PUBLIC_URL` | `http://localhost:5173` | Dashboard URL (Google redirect, alert links) |
| `AOBS_API_PUBLIC_URL` | `http://127.0.0.1:8000` | URL apps use for the gateway (shown on Connect page) |
| `AOBS_GOOGLE_CLIENT_ID` / `_SECRET` | empty | Enables Google sign-in |
| `AOBS_SMTP_HOST`, `_PORT`, `_USER`, `_PASSWORD`, `_FROM` | empty | Enables email alerts |
| `AOBS_DEV_API_KEY` | `dev-local-key` | Development-only key for the Main workspace |
| `AOBS_CORS_ORIGINS` | `http://localhost:5173,...` | Dashboard origins |
| `AOBS_AUTO_RETRAIN_EVERY` | `50` | Retrain after N new labels (0 = manual) |
| `AOBS_BACKGROUND_JOBS` | `true` | Window alerts, drift tests, retention, trial expiry (a DB lease lets one process run them) |
| `AOBS_PLATFORM_ADMINS` | empty | Comma-separated emails with access to the admin console |
| `AOBS_STRIPE_SECRET_KEY`, `_WEBHOOK_SECRET`, `_PRICE_PRO` | empty | Enables online billing |

Estimated costs use the price table in `backend/app/pricing.py`; update it to your rates.

## Limitations and next steps

- Training data is one kind of agent (SWE-agent fixing GitHub issues), with behavioral labels.
  Your agents use different tools; label their runs in the review queue to retrain on them, and
  watch the version history on the Detection models page.
- The intervention policy needs reviewed outcomes to learn; until then it follows the playbook.
- `ml/simulator.py` remains only for unit tests and experiments; nothing in the app uses it.
- Novelty is measured lexically (word bigrams). Swapping in sentence embeddings would catch
  paraphrased repetition better, at the cost of a model dependency.
- Analytics aggregate in Python over a time window; at high volume, move them to SQL views or a
  time-series store.
- Adapters for agent frameworks (LangChain/LangGraph callbacks, OpenTelemetry GenAI spans)
  would map their events onto the same step schema.
- LLM gateway: fallback models must be from the same provider (cross-provider fallback would need
  request/response translation). Block/repair modes buffer streamed responses until checked.
- Relevance and drift similarity are lexical; judge rules cover meaning, at the cost of a judge call.
- No password-reset email flow yet (Google sign-in or an admin can help a locked-out user);
  sign-in throttling is per process.
- Schema changes are Alembic migrations (`backend/migrations`), applied automatically at startup.
- Rate limits and live updates are per process. With several API processes behind a load balancer,
  move them to a shared store (e.g. Redis); the endpoints and event shapes stay the same.
