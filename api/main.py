"""FastAPI service: ingest agent traces, score them for anomalies, and
recommend an action via the RL policy.

Run with:
    python scripts/train_pipeline.py   # once, to produce model artifacts
    uvicorn api.main:app --reload
"""
from __future__ import annotations

import os
import pickle
from typing import Any, Dict, List, Optional

import numpy as np
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent_harness.trace_schema import Trace
from anomaly_model.model import AnomalyDetector
from api.database import get_db, TraceRecord
from embedding_pipeline.embedder import TraceEmbedder
from rl_policy.bandit import LinUCBBandit
from sqlalchemy.orm import Session

# Import auth and rate limiting
from api.auth import get_current_user
from api.rate_limiter import RateLimiter

# Import monitoring (optional, graceful degradation)
try:
    from api.monitoring import metrics_endpoint
    MONITORING_AVAILABLE = True
except ImportError:
    MONITORING_AVAILABLE = False

app = FastAPI(title="Agentic AI Silent-Failure Detector", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize rate limiter
rate_limiter = RateLimiter()

def check_rate_limit(request: Request) -> None:
    """Dependency to check rate limiting."""
    user_id = request.client.host  # Use IP address
    allowed, retry_after = rate_limiter.check_rate_limit(user_id, rate=100, per=60)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Retry after {retry_after}s",
            headers={"Retry-After": str(retry_after)}
        )


ARTIFACTS_DIR = os.environ.get("ARTIFACTS_DIR", "artifacts")
EMBEDDER_PATH = os.path.join(ARTIFACTS_DIR, "embedder.pkl")
DETECTOR_PATH = os.path.join(ARTIFACTS_DIR, "detector.pkl")
BANDIT_STATE_PATH = os.path.join(ARTIFACTS_DIR, "bandit_state.npz")

_embedder: Optional[TraceEmbedder] = None
_detector: Optional[AnomalyDetector] = None
_bandit = LinUCBBandit(n_features=5)


def _load_bandit_state():
    """Load persisted RL policy state."""
    global _bandit
    if os.path.exists(BANDIT_STATE_PATH):
        try:
            data = np.load(BANDIT_STATE_PATH)
            for action in _bandit.actions:
                if f"A_{action}" in data and f"b_{action}" in data:
                    _bandit._A[action] = data[f"A_{action}"]
                    _bandit._b[action] = data[f"b_{action}"]
            print(f"✅ Loaded RL policy state from {BANDIT_STATE_PATH}")
        except Exception as e:
            print(f"⚠️  Failed to load bandit state: {e}")
    else:
        print("ℹ️  No saved RL policy found, starting fresh")


def _save_bandit_state():
    """Persist RL policy state to disk."""
    try:
        save_dict = {}
        for action in _bandit.actions:
            save_dict[f"A_{action}"] = _bandit._A[action]
            save_dict[f"b_{action}"] = _bandit._b[action]
        np.savez(BANDIT_STATE_PATH, **save_dict)
        print(f"✅ Saved RL policy state to {BANDIT_STATE_PATH}")
    except Exception as e:
        print(f"⚠️  Failed to save bandit state: {e}")


@app.on_event("startup")
async def startup_event():
    """Load models and RL policy on startup."""
    _load_artifacts()
    _load_bandit_state()


@app.on_event("shutdown")
async def shutdown_event():
    """Save RL policy on shutdown."""
    _save_bandit_state()

def _load_artifacts() -> None:
    global _embedder, _detector
    if _embedder is not None and _detector is not None:
        return
    if not (os.path.exists(EMBEDDER_PATH) and os.path.exists(DETECTOR_PATH)):
        raise RuntimeError("Model artifacts not found. Run `python scripts/train_pipeline.py` first.")
    with open(EMBEDDER_PATH, "rb") as f:
        _embedder = pickle.load(f)
    _detector = AnomalyDetector.load(DETECTOR_PATH)


# Health endpoint - public, no auth required, but rate limited
@app.get("/health")
async def health(request: Request, _rate: None = Depends(check_rate_limit)) -> Dict[str, str]:
    return {"status": "ok"}


# Pydantic Models
class StepIn(BaseModel):
    step_id: int
    action_type: str
    tool_name: Optional[str] = None
    arguments: Dict[str, Any] = {}
    output: str = ""
    latency_ms: float = 0.0
    tokens_used: int = 0


class TraceIn(BaseModel):
    trace_id: Optional[str] = None
    task_description: str = ""
    steps: List[StepIn]


class ScoreOut(BaseModel):
    trace_id: str
    isolation_score: float
    is_cluster_outlier: bool
    combined_score: float
    is_anomalous: bool
    recommended_action: str
    context_summary: List[float]


class FeedbackIn(BaseModel):
    context_summary: List[float]
    action: str
    reward: float


# Protected endpoints below require API key AND rate limiting
@app.post("/ingest_trace", response_model=ScoreOut)
async def ingest_trace(
    trace_in: TraceIn,
    request: Request,
    _auth: Dict = Depends(get_current_user),
    _rate: None = Depends(check_rate_limit),
    db: Session = Depends(get_db)
) -> ScoreOut:
    try:
        _load_artifacts()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    assert _embedder is not None and _detector is not None

    trace = Trace.from_dict(trace_in.dict())
    embedding = _embedder.transform([trace])[0]
    score = _detector.score(embedding.reshape(1, -1))[0]

    context = LinUCBBandit.build_context(embedding, score.combined_score)
    action = _bandit.select_action(context)

    # Save to PostgreSQL using SQLAlchemy
    db_trace = TraceRecord(
        trace_id=trace.trace_id,
        task_description=trace.task_description,
        trace_json=trace.to_dict(),
        isolation_score=score.isolation_score,
        is_cluster_outlier=score.is_cluster_outlier,
        combined_score=score.combined_score,
        is_anomalous=score.is_anomalous,
        policy_action=action,
        context_summary=context.tolist()
    )
    db.add(db_trace)
    db.commit()
    db.refresh(db_trace)

    return ScoreOut(
        trace_id=trace.trace_id,
        isolation_score=score.isolation_score,
        is_cluster_outlier=score.is_cluster_outlier,
        combined_score=score.combined_score,
        is_anomalous=score.is_anomalous,
        recommended_action=action,
        context_summary=context.tolist(),
    )

# Feedback counter for periodic saves
_feedback_counter = 0
_SAVE_INTERVAL = 10  # Save every 10 feedback updates


@app.post("/feedback")
async def feedback(
    fb: FeedbackIn,
    request: Request,
    _auth: Dict = Depends(get_current_user),
    _rate: None = Depends(check_rate_limit)
) -> Dict[str, str]:
    """Update the bandit policy once the real outcome of a recommended action is known."""
    global _feedback_counter
    
    context = np.array(fb.context_summary, dtype=np.float32)
    _bandit.update(context, fb.action, fb.reward)
    
    # Save bandit state periodically
    _feedback_counter += 1
    if _feedback_counter >= _SAVE_INTERVAL:
        _save_bandit_state()
        _feedback_counter = 0
    
    return {"status": "policy updated"}


@app.get("/traces")
async def get_traces(
    request: Request,
    limit: int = 50,
    _auth: Dict = Depends(get_current_user),
    _rate: None = Depends(check_rate_limit),
    db: Session = Depends(get_db)
) -> List[Dict[str, Any]]:
    """Get recent traces (auth required)."""
    traces = db.query(TraceRecord).order_by(TraceRecord.created_at.desc()).limit(limit).all()
    
    return [
        {
            "trace_id": t.trace_id,
            "task_description": t.task_description,
            "combined_score": t.combined_score,
            "is_anomalous": t.is_anomalous,
            "policy_action": t.policy_action,
            "created_at": t.created_at.timestamp() if t.created_at else 0,
        }
        for t in traces
    ]


@app.get("/stats")
async def stats(
    request: Request,
    _rate: None = Depends(check_rate_limit),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Get system statistics (public but rate limited)."""
    from sqlalchemy import func as sql_func
    
    total = db.query(sql_func.count(TraceRecord.id)).scalar() or 0
    anomalous = db.query(sql_func.count(TraceRecord.id)).filter(TraceRecord.is_anomalous == True).scalar() or 0
    avg_score = db.query(sql_func.avg(TraceRecord.combined_score)).scalar() or 0.0
    
    return {
        "total_traces": total,
        "anomalous_traces": anomalous,
        "avg_combined_score": float(avg_score)
    }


@app.get("/metrics")
async def metrics(request: Request, _rate: None = Depends(check_rate_limit)):
    """Prometheus metrics endpoint (public but rate limited)."""
    if MONITORING_AVAILABLE:
        return metrics_endpoint()
    else:
        # Return simple text if monitoring not available
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(
            "# Monitoring module not available\n"
            "# Install: pip install prometheus-client\n"
        )
