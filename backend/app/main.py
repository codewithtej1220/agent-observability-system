"""FastAPI application entrypoint.

    uvicorn app.main:app --reload --port 8000      (from backend/)
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import SessionLocal, init_db
from . import crypto
from .routes import router
from .llm import upstream, worker
from .llm.gateway import router as gateway_router
from .routes_account import router as account_router
from .routes_llm import router as llm_router
from .services.registry import registry

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
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
)
app.include_router(account_router)
app.include_router(router)
app.include_router(llm_router)
app.include_router(gateway_router)


@app.get("/health", tags=["system"])
def health():
    return {"status": "ok", "models_loaded": registry.ready,
            "model_version": registry.engine.version if registry.engine else None}
