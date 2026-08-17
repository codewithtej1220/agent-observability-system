# 🔍 Agent Observability System

**AI System** detecting silent failures in LLM agent pipelines using **Unsupervised Learning**, **Reinforcement Learning**, and **Supervised Learning** working together.

**Status:** Core functionality complete with real data, auth, and persistence ✅

---

## 🎯 Problem & Solution

### Problem
AI agents fail silently - they loop infinitely, thrash between tools, hallucinate operations, or burn tokens without progress. Traditional monitoring can't catch these behavioral failures.

### Solution
Three learning paradigms working together:
1. **Unsupervised (IsolationForest + HDBSCAN)** → Detects anomalies without labels
2. **Reinforcement (LinUCB Bandit)** → Learns optimal intervention actions (persists across restarts)
3. **Supervised (Feedback Loop)** → Improves from real outcomes

**NEW:** Now trained on **1,200+ real agent traces** from HuggingFace datasets!

---

## 🚀 Quick Start

See **[QUICK_START_UPDATED.md](QUICK_START_UPDATED.md)** for full instructions.

```bash
# 1. Setup
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
pip install datasets psycopg2-binary python-dotenv  # Real data + PostgreSQL

# 2. Configure database (create .env file)
# DATABASE_URL=postgresql://user:pass@host:5432/db
# See .env.example for template

# 3. Train with REAL data
python scripts/train_pipeline.py

# 4. Start API server  
uvicorn api.main:app --reload --port 8001

# 5. Start React dashboard
cd frontend && npm start

# 6. Open dashboard
# Browser opens automatically at http://localhost:3000
```

---

## ✨ What's New

### ✅ Week 2: PostgreSQL Migration (LATEST!)
- **Before**: SQLite database (single-instance)
- **After**: PostgreSQL on Supabase (production-grade)
- SQLAlchemy ORM integration
- Environment-based configuration (.env)
- Multi-instance deployment ready
- See **[WEEK2_POSTGRESQL_MIGRATION.md](WEEK2_POSTGRESQL_MIGRATION.md)** for details

### ✅ Week 1: Real Data & Security
- **Before**: 120 synthetic traces only
- **After**: 1,200+ real traces from HuggingFace (Exgentic, Who&When, BFCL datasets)
- Proper train/validation/test splits (64%/16%/20%)
- Honest evaluation on held-out test set

### ✅ Authentication Enforced
- **Before**: Code existed but not applied
- **After**: All protected endpoints require API key
- Default keys: `dev-key-12345`, `prod-key-67890`

### ✅ Rate Limiting Active
- **Before**: Code existed but not applied  
- **After**: 100 requests per minute limit enforced
- Token bucket algorithm prevents abuse

### ✅ RL Policy Persistence
- **Before**: Learning reset on every restart
- **After**: Saved to disk, persists across restarts
- Accumulates knowledge over time

See **[CRITICAL_FIXES_COMPLETE.md](CRITICAL_FIXES_COMPLETE.md)** for Week 1 details.

---

## 📊 What It Does

**Input:** Agent execution traces (tool calls, arguments, outputs, timing)
```json
{
  "task_description": "Search weather and summarize",
  "steps": [
    {"step_id": 0, "tool_name": "search", "arguments": {...}, "output": "..."},
    {"step_id": 1, "tool_name": "summarize", "arguments": {...}, "output": "..."}
  ]
}
```

**Output:** Anomaly detection + Action recommendation
```json
{
  "trace_id": "abc-123",
  "is_anomalous": true,
  "combined_score": 0.85,
  "recommended_action": "interrupt_human",
  "context_summary": [0.1, 0.2, 0.3, 0.4, 1.0]
}
```

**Detects:**
- 🔄 Infinite loops (same tool repeated)
- 🔀 Tool thrashing (random switching)
- 👻 Hallucinated tools (non-existent calls)
- 💰 Token burning (high cost, no progress)

---

## 🏗️ Architecture

```
React Dashboard → FastAPI API → [Unsupervised] → [RL Policy] → Response
                      ↓              ↓               ↓
                  SQLite      IsolationForest   LinUCB Bandit
                              + HDBSCAN         (Persisted)
                                                     ↓
                                                [Supervised]
                                               Feedback Loop
```

**Current Stack:**
- **Backend**: FastAPI with authentication + rate limiting
- **Database**: SQLite (PostgreSQL migration pending)
- **Frontend**: React with real-time updates
- **ML Models**: IsolationForest + HDBSCAN + LinUCB
- **Training Data**: Real traces from HuggingFace datasets

---

## ✅ Implemented Features

| Category | Status |
|----------|--------|
| **Core ML** | ✅ Unsupervised ✅ Reinforcement (persistent) ✅ Supervised ✅ |
| **Real Data** | ✅ 1,200+ traces from HuggingFace ✅ Train/val/test splits |
| **Backend** | ✅ FastAPI ✅ Auth enforced ✅ Rate limiting active |
| **Frontend** | ✅ React dashboard ✅ Real-time updates ✅ Auto-refresh |
| **Security** | ✅ API Key auth ✅ Rate limiting (100/min) |
| **Persistence** | ✅ RL policy saved to disk ✅ Survives restarts |
| **Testing** | ✅ System tests ✅ Load test scripts |

## 🚧 Pending Improvements

| Feature | Status | Priority |
|---------|--------|----------|
| PostgreSQL migration | Planned | Week 2 |
| Monitoring (Sentry DSN) | Config needed | Week 3 |
| CI/CD (GitHub Actions) | Ready to push | Week 3 |
| Deep learning integration | Code exists, not wired | Week 4 |
| Kubernetes deployment | Manifest untested | Optional |

See **[PROJECT_FLAWS_AND_LIMITATIONS.md](PROJECT_FLAWS_AND_LIMITATIONS.md)** for honest assessment.

---

## 📖 Key Documentation

| File | Purpose |
|------|---------|
| **[QUICK_START_UPDATED.md](QUICK_START_UPDATED.md)** | Complete setup guide with new features |
| **[CRITICAL_FIXES_COMPLETE.md](CRITICAL_FIXES_COMPLETE.md)** | Week 1 fixes implementation summary |
| **[PROJECT_FLAWS_AND_LIMITATIONS.md](PROJECT_FLAWS_AND_LIMITATIONS.md)** | Honest assessment of gaps |
| **[WEEK1_FIXES_IMPLEMENTED.md](WEEK1_FIXES_IMPLEMENTED.md)** | Detailed fix documentation |
| **ALL_THREE_LEARNING_TYPES.md** | ML architecture details |

---

## 🔧 API Endpoints

```
GET  /health           - Health check (rate limited, no auth)
GET  /stats            - System statistics (rate limited, no auth)
POST /ingest_trace     - Submit agent traces (requires auth + rate limit)
POST /feedback         - Provide outcome feedback (requires auth + rate limit)
GET  /traces           - Get recent traces (requires auth + rate limit)
GET  /metrics          - Prometheus metrics (rate limited, no auth)
GET  /docs             - Interactive API docs
```

**Authentication:**
```bash
# With API Key (required for protected endpoints)
curl -H "X-API-Key: dev-key-12345" \
     -H "Content-Type: application/json" \
     -X POST http://localhost:8001/ingest_trace \
     -d '{"task_description":"test","steps":[]}'

# Without auth (will fail with 401)
curl -X POST http://localhost:8001/ingest_trace -d '{}'
```

**Rate Limiting:**
- Limit: 100 requests per minute per endpoint
- Excess requests receive HTTP 429

---

## 🧪 Testing

```bash
# Train with real data
python scripts/train_pipeline.py

# Run system tests
python test_complete_system.py

# Test authentication
curl http://localhost:8001/ingest_trace -X POST -d '{}'
# Should return 401 Unauthorized

# Test rate limiting
for i in {1..105}; do curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8001/health; done
# Should show some 429 responses

# Demo all learning types
python demo_all_learning_types.py
```

---

## 🐳 Deployment

### Current Status
- ✅ **Local development**: Fully working
- ⚠️ **Docker Compose**: Created but untested
- ⚠️ **Kubernetes**: Manifest created but untested
- 🚧 **Cloud deployment**: Pending

### Recommended Path
```bash
# 1. Test locally first
python scripts/train_pipeline.py
uvicorn api.main:app --reload --port 8001

# 2. Then try Docker (needs testing)
docker-compose up -d

# 3. For production, consider simpler platforms first
# - Railway.app
# - Render.com  
# - Fly.io
```

---

## 🎓 How It Works

1. **Trace Arrives** → Extract features (tool diversity, repetition, errors, timing)
2. **Unsupervised Detection** → IsolationForest + HDBSCAN → Anomaly score  
3. **RL Decision** → LinUCB Bandit (persistent) → Recommended action
4. **System Executes** → Action taken in real world
5. **Supervised Learning** → Feedback received → Policy updates and persists

**RL Learning Now Persists:** Policy matrices saved every 10 feedback updates and on shutdown!

---

## 💾 Database

**Current:** SQLite (`traces.db`)
- ✅ Works for single-instance deployment
- ✅ Simple, no external dependencies
- ⚠️ Not suitable for multi-instance/high-traffic

**Future:** PostgreSQL migration planned (Week 2)

---

## 🔐 Security

**Implemented:**
- ✅ API Key authentication (enforced on protected endpoints)
- ✅ Rate limiting (token bucket, 100 req/min)
- ✅ Input validation (Pydantic models)
- ✅ CORS configuration

**Pending:**
- 🚧 JWT token support (code exists, not integrated)
- 🚧 RBAC (code exists, not enforced)
- 🚧 Sentry error tracking (needs DSN configuration)

---

## 📈 Current Capabilities

**What Works:**
- ✅ Train on 1,200+ real agent traces
- ✅ Proper train/validation/test evaluation
- ✅ Detect anomalies in agent behavior
- ✅ Recommend interventions via RL
- ✅ Learn from feedback (persistent)
- ✅ Secure API with auth + rate limiting
- ✅ Real-time React dashboard
- ✅ Auto-refresh metrics

**What's Pending:**
- 🚧 PostgreSQL (SQLite works but limited scale)
- 🚧 Monitoring stack (Sentry/Grafana - needs config)
- 🚧 CI/CD pipeline (ready to push to GitHub)
- 🚧 Deep learning model (code exists, not wired in)
- 🚧 Kubernetes (manifest untested)

---

## 🎉 Week 1 Achievements

✅ **Real Data**: Trained on actual agent traces, not synthetic  
✅ **Honest Metrics**: Evaluated on held-out test set
✅ **Auth Working**: Actually enforced, not just code  
✅ **Rate Limiting**: Actually applied, prevents abuse
✅ **RL Persistence**: Learning survives restarts
✅ **Professional UI**: React dashboard with glassmorphism

**Assessment:**
- Before: Proof of concept (2/10 production-ready)
- After: Core functionality solid (7/10 production-ready)
- Next: Infrastructure decisions + monitoring (target 9/10)

---

## 📞 Support & Documentation

- **Setup Issues:** [QUICK_START_UPDATED.md](QUICK_START_UPDATED.md)
- **What Changed:** [CRITICAL_FIXES_COMPLETE.md](CRITICAL_FIXES_COMPLETE.md)
- **Known Gaps:** [PROJECT_FLAWS_AND_LIMITATIONS.md](PROJECT_FLAWS_AND_LIMITATIONS.md)
- **ML Details:** ALL_THREE_LEARNING_TYPES.md

---

## 🏆 Current State

**This project:**
- ✅ Demonstrates all 3 learning paradigms working together
- ✅ Uses real data from production agent benchmarks  
- ✅ Has honest train/test evaluation
- ✅ Implements actual security (not just code)
- ✅ Persists learning across restarts
- ✅ Has professional frontend

**It's ready for:**
- Portfolio demonstration
- Solo/small team deployment
- Local development and testing
- MVP/proof of concept

**It needs for true production:**
- Database decision (PostgreSQL or own SQLite limitation)
- Monitoring configuration (Sentry DSN, etc.)
- Load testing and optimization
- CI/CD pipeline activation

**Honest next steps:** Week 2-4 improvements documented in critical fixes files.

---

**Let's be honest and ship incrementally! 🚀**
