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
- **Early Alerts** - Detects issues 1-2 steps after onset (89% of the time)
- **Smart Interventions** - RL policy learns which actions work best
- **Rich Dashboard** - Full observability with graphs, heatmaps, and flow diagrams
- **Continuous Learning** - Gets smarter from human feedback
- **Cost Savings** - Prevents up to 70% of wasted tokens in failing runs
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

## Results (simulated reference data)

Measured on 1,500 held-out simulated runs (≈25% failing) that were never used for training.
The simulator deliberately includes healthy behavior that looks like failure (pagination,
polling a job until it finishes, retry after a transient error, productive A↔B alternation).
**Expect lower numbers on real traffic** — the review queue and retraining are how the models
adapt to it.

| | Precision | Recall | False-positive rate | Caught ≤ 2 steps after onset | Avoidable tokens flagged |
|---|---|---|---|---|---|
| Fused engine (v1) | 97.3% | 98.1% | 0.9% | 89% | 70% of failing-run tokens |

**Each paradigm alone vs fused** (recall at 5% FPR): rules 0%, unsupervised 56%, supervised 100%, fused 100%.

**The case that matters in production — a failure type never seen in training** (leave-one-type-out):

| Held-out type | Rules only | Unsupervised only | Supervised only | **Fused** |
|---|---|---|---|---|
| Loop | 83% @ 24% FPR | 99% @ 30% FPR | 17% @ 0% FPR | **59% @ 1.3% FPR** |
| Tool thrashing | 45% @ 24% | 99% @ 30% | 82% @ 0.1% | **84% @ 1.7%** |
| Hallucinated tool | 100% @ 24% | 59% @ 28% | 37% @ 0% | **100% @ 1.1%** |
| Token waste | 68% @ 24% | 96% @ 30% | 89% @ 0% | **89% @ 1.0%** |

A supervised model alone confidently calls unfamiliar failures "healthy"; rules and novelty
alone flag a quarter of healthy runs. Combined, they keep false positives near 1% while
recovering most of the lost recall.

**Intervention policy** (average reward over 4,000 simulated decisions; oracle = upper bound
that knows the true failure): LinUCB **0.58**, hand-written playbook 0.41, always page a human
0.37, random 0.35, oracle 0.65.

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

# Bootstrap: train models + seed demo data (~2-3 minutes)
python -m scripts.bootstrap

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
  seeded *Demo workspace* (simulated agent runs and LLM calls); later sign-ups get their own workspace.
- API Docs: http://localhost:8000/docs
- Health Check: http://localhost:8000/health

**Stream Live Traffic (optional):**
```bash
# Run simulated agent traffic
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
        if verdict and verdict.action == "reflect":
            messages.append(REFLECTION_PROMPT)       # e.g. "You are repeating the same call..."
    run.final_answer(answer)

# Later, once the outcome is known (closes the learning loop):
client.feedback(run.run_id, label="healthy", resolved=True)
```

The client fails open: if the service is unreachable, the agent keeps running.
In development, `dev-local-key` also works and maps to the Demo workspace (disabled when
`AOBS_ENVIRONMENT=production` and in Docker Compose).

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

## Dashboard Features

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
    simulator.py   # Agent behavior simulator
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
    bootstrap.py   # Setup: train + seed demo data
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
# Bootstrap automatically seeds demo data
cd backend
python -m scripts.bootstrap

# Or generate live traffic:
python sdk/examples/live_traffic.py --runs 50
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
| `AOBS_DEV_API_KEY` | `dev-local-key` | Development-only key for the Demo workspace |
| `AOBS_CORS_ORIGINS` | `http://localhost:5173,...` | Dashboard origins |
| `AOBS_AUTO_RETRAIN_EVERY` | `50` | Retrain after N new labels (0 = manual) |
| `AOBS_BACKGROUND_JOBS` | `true` | Window alerts, drift tests, retention (run in one process only) |

Estimated costs use the price table in `backend/app/pricing.py`; update it to your rates.

## Limitations and next steps

- Reference metrics come from a simulator. Run on real traffic, label through the review
  queue, and watch the version history on the Detection models page.
- The policy's offline warm start uses an assumed outcome model (`ml/simulator.py`,
  `SUCCESS_PROB`). Live rewards from reviews override it over time.
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
- Background jobs run inside the API process; with several API workers, enable them on one only.
