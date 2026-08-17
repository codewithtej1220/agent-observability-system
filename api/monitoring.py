"""Prometheus metrics and health monitoring.

Metrics tracked:
- Request count by endpoint
- Request duration by endpoint
- Error rate
- Model prediction latency
- Trace ingestion rate
- Anomaly detection rate
"""
from __future__ import annotations

import os
import time
from typing import Callable

from fastapi import Request, Response
from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    Info,
    generate_latest,
    CONTENT_TYPE_LATEST,
)
from starlette.responses import Response as StarletteResponse

# ============================================================================
# PROMETHEUS METRICS
# ============================================================================

# Application info
app_info = Info("app", "Application information")
app_info.info({
    "version": "1.0.0",
    "environment": os.getenv("ENVIRONMENT", "development")
})

# HTTP metrics
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"]
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"]
)

http_requests_in_progress = Gauge(
    "http_requests_in_progress",
    "HTTP requests currently in progress",
    ["method", "endpoint"]
)

# Business metrics
traces_ingested_total = Counter(
    "traces_ingested_total",
    "Total number of traces ingested",
    ["is_anomalous"]
)

anomaly_score_histogram = Histogram(
    "anomaly_score",
    "Distribution of anomaly scores",
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
)

model_prediction_duration_seconds = Histogram(
    "model_prediction_duration_seconds",
    "Model prediction duration in seconds",
    ["model_name"]
)

feedback_received_total = Counter(
    "feedback_received_total",
    "Total feedback signals received",
    ["action", "outcome"]
)

# System metrics
database_connections_active = Gauge(
    "database_connections_active",
    "Active database connections"
)

rate_limit_exceeded_total = Counter(
    "rate_limit_exceeded_total",
    "Total number of rate limit violations",
    ["user"]
)

auth_failures_total = Counter(
    "auth_failures_total",
    "Total authentication failures",
    ["reason"]
)


# ============================================================================
# METRICS MIDDLEWARE
# ============================================================================


async def metrics_middleware(request: Request, call_next: Callable) -> Response:
    """Collect metrics for each request."""
    # Skip metrics endpoint itself
    if request.url.path == "/metrics":
        return await call_next(request)
    
    method = request.method
    endpoint = request.url.path
    
    # Track in-progress requests
    http_requests_in_progress.labels(method=method, endpoint=endpoint).inc()
    
    start_time = time.time()
    
    try:
        response = await call_next(request)
        status_code = response.status_code
    except Exception as e:
        status_code = 500
        raise
    finally:
        # Record metrics
        duration = time.time() - start_time
        
        http_requests_total.labels(
            method=method,
            endpoint=endpoint,
            status_code=status_code
        ).inc()
        
        http_request_duration_seconds.labels(
            method=method,
            endpoint=endpoint
        ).observe(duration)
        
        http_requests_in_progress.labels(method=method, endpoint=endpoint).dec()
    
    return response


# ============================================================================
# METRICS ENDPOINT
# ============================================================================


def metrics_endpoint() -> StarletteResponse:
    """Expose Prometheus metrics."""
    return StarletteResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# ============================================================================
# BUSINESS METRICS HELPERS
# ============================================================================


def record_trace_ingestion(is_anomalous: bool, score: float):
    """Record trace ingestion metrics."""
    traces_ingested_total.labels(is_anomalous=str(is_anomalous)).inc()
    anomaly_score_histogram.observe(score)


def record_model_prediction(model_name: str, duration: float):
    """Record model prediction metrics."""
    model_prediction_duration_seconds.labels(model_name=model_name).observe(duration)


def record_feedback(action: str, outcome: str):
    """Record feedback metrics."""
    feedback_received_total.labels(action=action, outcome=outcome).inc()


def record_rate_limit_exceeded(user: str):
    """Record rate limit violation."""
    rate_limit_exceeded_total.labels(user=user).inc()


def record_auth_failure(reason: str):
    """Record authentication failure."""
    auth_failures_total.labels(reason=reason).inc()


# ============================================================================
# HEALTH CHECK
# ============================================================================


def get_health_status() -> dict:
    """Get comprehensive health status."""
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "checks": {
            "database": check_database_health(),
            "models": check_models_health(),
            "memory": check_memory_health(),
        }
    }


def check_database_health() -> dict:
    """Check database health."""
    try:
        from api.storage import get_connection
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        return {"status": "healthy", "message": "Database connection OK"}
    except Exception as e:
        return {"status": "unhealthy", "message": str(e)}


def check_models_health() -> dict:
    """Check if models are loaded."""
    import os
    
    embedder_exists = os.path.exists("artifacts/embedder.pkl")
    detector_exists = os.path.exists("artifacts/detector.pkl")
    
    if embedder_exists and detector_exists:
        return {"status": "healthy", "message": "Models loaded"}
    else:
        return {
            "status": "unhealthy",
            "message": "Models not found. Run train_pipeline.py"
        }


def check_memory_health() -> dict:
    """Check memory usage."""
    try:
        import psutil
        memory = psutil.virtual_memory()
        usage_percent = memory.percent
        
        if usage_percent > 90:
            status = "critical"
        elif usage_percent > 75:
            status = "warning"
        else:
            status = "healthy"
        
        return {
            "status": status,
            "usage_percent": usage_percent,
            "available_mb": memory.available // (1024 * 1024)
        }
    except ImportError:
        return {"status": "unknown", "message": "psutil not installed"}
