"""Centralized logging and error tracking configuration.

Features:
- Structured JSON logging
- Log levels per environment
- Request/response logging
- Error tracking with Sentry
- Performance metrics
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
import traceback
from datetime import datetime
from typing import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = os.getenv("LOG_FORMAT", "json")  # 'json' or 'text'
SENTRY_DSN = os.getenv("SENTRY_DSN", None)


class JSONFormatter(logging.Formatter):
    """Format logs as JSON for structured logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": traceback.format_exception(*record.exc_info)
            }
        
        # Add extra fields
        if hasattr(record, "extra"):
            log_data.update(record.extra)
        
        return json.dumps(log_data)


def setup_logging():
    """Configure application logging."""
    # Root logger
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, LOG_LEVEL.upper()))
    
    # Remove existing handlers
    logger.handlers.clear()
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    
    if LOG_FORMAT == "json":
        console_handler.setFormatter(JSONFormatter())
    else:
        console_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
        )
    
    logger.addHandler(console_handler)
    
    # File handler for production
    if os.getenv("ENVIRONMENT") == "production":
        file_handler = logging.FileHandler("logs/app.log")
        file_handler.setFormatter(JSONFormatter())
        logger.addHandler(file_handler)
    
    return logger


# Initialize logger
logger = setup_logging()


# ============================================================================
# SENTRY INTEGRATION
# ============================================================================

sentry_sdk = None
if SENTRY_DSN:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
        
        sentry_sdk.init(
            dsn=SENTRY_DSN,
            environment=os.getenv("ENVIRONMENT", "development"),
            traces_sample_rate=0.1,  # 10% of transactions for performance monitoring
            integrations=[
                FastApiIntegration(),
                SqlalchemyIntegration(),
            ],
        )
        logger.info("Sentry error tracking initialized")
    except ImportError:
        logger.warning("Sentry SDK not installed. Run: pip install sentry-sdk")
        sentry_sdk = None


# ============================================================================
# REQUEST/RESPONSE LOGGING MIDDLEWARE
# ============================================================================


async def logging_middleware(request: Request, call_next: Callable) -> Response:
    """Log all requests and responses with timing."""
    request_id = request.headers.get("X-Request-ID", f"req_{int(time.time() * 1000)}")
    start_time = time.time()
    
    # Log request
    logger.info(
        "Incoming request",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "query_params": dict(request.query_params),
            "client_ip": request.client.host,
            "user_agent": request.headers.get("user-agent"),
        }
    )
    
    # Process request
    try:
        response = await call_next(request)
        
        # Calculate duration
        duration = time.time() - start_time
        
        # Log response
        logger.info(
            "Request completed",
            extra={
                "request_id": request_id,
                "status_code": response.status_code,
                "duration_ms": round(duration * 1000, 2),
            }
        )
        
        # Add request ID to response headers
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = f"{duration:.4f}"
        
        return response
    
    except Exception as e:
        duration = time.time() - start_time
        
        # Log error
        logger.error(
            "Request failed",
            extra={
                "request_id": request_id,
                "duration_ms": round(duration * 1000, 2),
                "error": str(e),
                "error_type": type(e).__name__,
            },
            exc_info=True
        )
        
        # Send to Sentry if configured
        if sentry_sdk:
            sentry_sdk.capture_exception(e)
        
        # Return error response
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "request_id": request_id,
                "message": str(e) if os.getenv("DEBUG") == "true" else "An error occurred"
            },
            headers={"X-Request-ID": request_id}
        )


# ============================================================================
# STRUCTURED LOGGING HELPERS
# ============================================================================


def log_trace_ingestion(trace_id: str, is_anomalous: bool, score: float):
    """Log trace ingestion event."""
    logger.info(
        "Trace ingested",
        extra={
            "event": "trace_ingestion",
            "trace_id": trace_id,
            "is_anomalous": is_anomalous,
            "anomaly_score": score,
        }
    )


def log_feedback_received(trace_id: str, action: str, reward: float):
    """Log feedback event."""
    logger.info(
        "Feedback received",
        extra={
            "event": "feedback",
            "trace_id": trace_id,
            "action": action,
            "reward": reward,
        }
    )


def log_model_prediction(model_name: str, duration_ms: float, input_shape: tuple):
    """Log model prediction event."""
    logger.info(
        "Model prediction",
        extra={
            "event": "model_prediction",
            "model": model_name,
            "duration_ms": duration_ms,
            "input_shape": input_shape,
        }
    )


def log_security_event(event_type: str, user: str, details: dict):
    """Log security-related events."""
    logger.warning(
        "Security event",
        extra={
            "event": "security",
            "type": event_type,
            "user": user,
            **details
        }
    )


# ============================================================================
# PERFORMANCE MONITORING
# ============================================================================


class PerformanceMonitor:
    """Context manager for monitoring code block performance."""
    
    def __init__(self, operation_name: str):
        self.operation_name = operation_name
        self.start_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        
        if exc_type:
            logger.error(
                f"Operation failed: {self.operation_name}",
                extra={
                    "operation": self.operation_name,
                    "duration_ms": round(duration * 1000, 2),
                    "error": str(exc_val),
                }
            )
        else:
            logger.debug(
                f"Operation completed: {self.operation_name}",
                extra={
                    "operation": self.operation_name,
                    "duration_ms": round(duration * 1000, 2),
                }
            )
        
        return False  # Don't suppress exceptions
