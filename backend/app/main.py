"""FastAPI application entrypoint.

    uvicorn app.main:app --reload --port 8000      (from backend/)
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import SessionLocal, init_db
from . import crypto
from .routes import router
from .llm import upstream, worker
from .llm.gateway import router as gateway_router
from .realtime import broker
from .routes_account import router as account_router
from .routes_billing import router as billing_router
from .routes_llm import router as llm_router
from .routes_studio import router as studio_router
from .services.registry import registry

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    broker.bind(asyncio.get_running_loop())
    crypto.check_ready()
    db = SessionLocal()
    try:
        registry.load(db)
    finally:
        db.close()
    task = asyncio.create_task(worker.run_forever()) if settings.background_jobs else None
    yield
    if task is not None:
        task.cancel()
    await upstream.close()
    registry.save_policy()


settings = get_settings()
app = FastAPI(
    title="Agent Observability API",
    version="2.0.0",
    description="Detects silent failures in LLM agents (loops, tool thrashing, hallucinated tools, "
                "token waste) and recommends interventions.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["X-API-Key", "Content-Type", "X-Requested-With", "Authorization"],
    expose_headers=["X-Request-ID"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    """Request IDs for tracing, and safe default security headers."""
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex
    response = await call_next(request)
    response.headers.setdefault("X-Request-ID", rid)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    if request.url.scheme == "https":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


app.include_router(account_router)
app.include_router(billing_router)
app.include_router(router)
app.include_router(llm_router)
app.include_router(studio_router)
app.include_router(gateway_router)


@app.get("/health", tags=["system"])
def health():
    return {"status": "ok", "models_loaded": registry.ready,
            "model_version": registry.engine.version if registry.engine else None}


@app.get("/health/ready", tags=["system"])
def ready():
    """Readiness: the database answers and the models are loaded."""
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"status": "unavailable", "database": str(e)[:200]}, status_code=503)
    if not registry.ready:
        return JSONResponse({"status": "starting", "database": "ok", "models_loaded": False}, status_code=503)
    return {"status": "ok", "database": "ok", "models_loaded": True}
