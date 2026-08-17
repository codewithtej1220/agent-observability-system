# System Architecture

## Overview

Agent Observability System uses three machine learning paradigms working together to detect silent failures in LLM agent pipelines.

## High-Level Architecture

```
┌─────────────────┐
│   Agent Trace   │
│   (JSON Input)  │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│     FastAPI Backend (Port 8001)         │
│  ┌───────────────────────────────────┐  │
│  │  1. Feature Extraction            │  │
│  │     - Tool diversity              │  │
│  │     - Repetition patterns         │  │
│  │     - Error frequency             │  │
│  │     - Latency stats               │  │
│  └───────────────────────────────────┘  │
│                 │                        │
│                 ▼                        │
│  ┌───────────────────────────────────┐  │
│  │  2. Anomaly Detection             │  │
│  │     - IsolationForest             │  │
│  │     - HDBSCAN Clustering          │  │
│  │     → Combined Score              │  │
│  └───────────────────────────────────┘  │
│                 │                        │
│                 ▼                        │
│  ┌───────────────────────────────────┐  │
│  │  3. Action Selection (RL)         │  │
│  │     - LinUCB Bandit               │  │
│  │     - Context-aware decisions     │  │
│  │     → Recommended Action          │  │
│  └───────────────────────────────────┘  │
│                 │                        │
│                 ▼                        │
│  ┌───────────────────────────────────┐  │
│  │  4. Storage (PostgreSQL)          │  │
│  │     - Trace records               │  │
│  │     - Feedback signals            │  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│   React Dashboard (Port 3000)           │
│   - Real-time metrics                   │
│   - Anomaly visualization               │
│   - Action recommendations              │
└─────────────────────────────────────────┘
```

## Component Details

### 1. Feature Extraction (`embedding_pipeline/`)

**Purpose:** Convert raw agent traces into numerical feature vectors

**Features Extracted:**
- `tool_diversity`: unique_tools / total_steps
- `max_repetition`: longest sequence of identical tool calls
- `error_rate`: failed_steps / total_steps
- `avg_latency`: mean response time
- `token_efficiency`: tokens_per_step

**Implementation:** `TraceEmbedder` class

### 2. Anomaly Detection (`anomaly_model/`)

**Purpose:** Identify abnormal agent behavior patterns

**Two-Stage Detection:**

**Stage 1: IsolationForest**
- Unsupervised outlier detection
- Works in high-dimensional feature space
- Outputs isolation score (0-1)

**Stage 2: HDBSCAN Clustering**
- Density-based clustering
- Identifies traces outside normal clusters
- Outputs is_cluster_outlier (boolean)

**Combined Scoring:**
```python
combined_score = 0.6 * isolation_score + 0.4 * is_cluster_outlier
is_anomalous = combined_score > threshold (0.5)
```

### 3. Reinforcement Learning (`rl_policy/`)

**Purpose:** Learn optimal intervention actions based on context

**Algorithm:** LinUCB (Contextual Bandit)
- Balances exploration vs exploitation
- Updates policy from feedback
- Persistent across restarts

**Actions:**
- `continue` - Let agent proceed
- `pause` - Stop and await human review
- `retry` - Retry failed operation
- `abort` - Terminate agent execution

**Context Features:**
- Anomaly scores
- Feature vector summary
- Historical performance

**Policy Update:**
```python
# On feedback:
A_action = A_action + context * context.T
b_action = b_action + reward * context
```

### 4. Database Layer (`api/database.py`)

**Technology:** PostgreSQL with SQLAlchemy ORM

**Schema:**

**traces table:**
```sql
CREATE TABLE traces (
    id SERIAL PRIMARY KEY,
    trace_id VARCHAR UNIQUE,
    task_description VARCHAR,
    trace_json JSONB,
    isolation_score FLOAT,
    is_cluster_outlier BOOLEAN,
    combined_score FLOAT,
    is_anomalous BOOLEAN,
    policy_action VARCHAR,
    context_summary JSONB,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

**feedback table:**
```sql
CREATE TABLE feedback (
    id SERIAL PRIMARY KEY,
    trace_id VARCHAR,
    action VARCHAR,
    reward FLOAT,
    outcome VARCHAR,
    context_summary JSONB,
    created_at TIMESTAMP
);
```

**Indexes:**
- `trace_id` (unique)
- `combined_score`
- `is_anomalous`
- `created_at`

### 5. API Layer (`api/main.py`)

**Framework:** FastAPI with async support

**Key Endpoints:**

**POST /ingest_trace**
- Accepts agent trace
- Runs through detection pipeline
- Returns scores and recommended action
- Saves to database
- **Auth:** Required (API key)

**POST /feedback**
- Updates RL policy with outcome
- Improves future recommendations
- **Auth:** Required

**GET /traces**
- Retrieves recent traces
- **Auth:** Required

**GET /stats**
- System statistics
- **Auth:** Not required (rate limited)

**GET /health**
- Health check
- **Auth:** Not required (rate limited)

### 6. Security Layer

**Authentication (`api/auth.py`):**
- API key validation
- Role-based access control (RBAC)
- JWT token support (not activated)

**Rate Limiting (`api/rate_limiter.py`):**
- Token bucket algorithm
- Per-user limits (100 req/min default)
- Configurable per endpoint

**Data Protection:**
- Environment variables for secrets
- SQL injection prevention (ORM)
- Input validation (Pydantic)
- CORS configuration

### 7. Frontend (`frontend/src/`)

**Technology:** React 18 with hooks

**Components:**
- Real-time metrics dashboard
- Anomaly score visualization
- Trace history table
- Action distribution charts

**API Integration:**
- Fetch with API key header
- Auto-refresh every 5 seconds
- Error handling and retry logic

## Data Flow

### Ingestion Flow
```
1. Client sends trace → POST /ingest_trace
2. API validates request → Pydantic schema
3. Extract features → TraceEmbedder
4. Detect anomalies → IsolationForest + HDBSCAN
5. Select action → LinUCB Bandit
6. Save to database → PostgreSQL
7. Return response → JSON with scores
```

### Feedback Loop
```
1. Human reviews agent outcome
2. Client sends feedback → POST /feedback
3. RL policy updates → LinUCB matrices
4. Policy persists → artifacts/bandit_state.npz
5. Future predictions improve
```

### Dashboard Flow
```
1. React app requests data → GET /traces, GET /stats
2. API queries database → SQLAlchemy
3. Response formatted → JSON
4. Charts update → Recharts
5. Auto-refresh in 5s → useEffect timer
```

## Model Training

**Training Pipeline:** `scripts/train_pipeline.py`

**Process:**
1. Load real traces from HuggingFace datasets
2. Extract features for all traces
3. Split: 64% train, 16% validation, 20% test
4. Train IsolationForest on train set
5. Train HDBSCAN on train embeddings
6. Evaluate on test set (never seen during training)
7. Save models to `artifacts/`

**Model Persistence:**
- `artifacts/embedder.pkl` - Feature extractor
- `artifacts/detector.pkl` - Anomaly detector
- `artifacts/bandit_state.npz` - RL policy (auto-saved)

## Deployment Architecture

### Local Development
```
Terminal 1: uvicorn api.main:app --reload --port 8001
Terminal 2: cd frontend && npm start
Database: Supabase PostgreSQL (cloud)
```

### Docker Deployment
```yaml
services:
  api:
    build: .
    ports: ["8001:8001"]
    environment:
      DATABASE_URL: ${DATABASE_URL}
  frontend:
    build: ./frontend
    ports: ["3000:3000"]
```

### Kubernetes Deployment
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: agent-observability-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: agent-observability
  template:
    spec:
      containers:
      - name: api
        image: agent-observability:latest
        ports:
        - containerPort: 8001
```

## Performance Characteristics

**API Latency:**
- Feature extraction: ~5ms
- Anomaly detection: ~10ms
- Database write: ~5ms
- **Total:** <100ms (p95)

**Throughput:**
- 100+ concurrent requests
- Rate limited to 100 req/min per user

**Database:**
- Connection pool: 10 base + 20 overflow
- Query performance: <5ms for recent traces
- Horizontal scaling supported

## Technology Stack Summary

**Backend:**
- Python 3.8+
- FastAPI 0.100+
- SQLAlchemy (ORM)
- PostgreSQL 13+
- scikit-learn
- NumPy

**Frontend:**
- React 18
- Recharts
- Modern CSS

**Infrastructure:**
- Docker
- Kubernetes
- GitHub Actions
- Supabase (PostgreSQL hosting)

**ML/AI:**
- IsolationForest (anomaly detection)
- HDBSCAN (clustering)
- LinUCB (reinforcement learning)
- Custom feature engineering

## Design Decisions

**Why PostgreSQL?**
- Horizontal scaling capability
- Production-grade reliability
- JSON support for flexible schemas
- Multi-instance compatibility

**Why LinUCB?**
- Context-aware action selection
- Balances exploration/exploitation
- Simple to implement and debug
- No deep learning complexity

**Why IsolationForest + HDBSCAN?**
- Unsupervised (no labels needed)
- Fast inference
- Interpretable scores
- Complementary approaches

**Why FastAPI?**
- Modern async support
- Automatic API documentation
- Fast performance
- Strong typing with Pydantic

**Why React?**
- Component-based architecture
- Rich ecosystem
- Real-time updates easy to implement
- Professional UI capabilities
