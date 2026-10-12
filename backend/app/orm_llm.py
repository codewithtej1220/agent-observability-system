"""Database tables for LLM monitoring."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
from .orm import utcnow

CONTRACT_MODES = ("monitor", "block", "repair")


class Contract(Base):
    """A prompt contract: the rules responses for a project must follow, and what to do on violation."""

    __tablename__ = "contracts"
    __table_args__ = (UniqueConstraint("workspace_id", "slug"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(64))  # sent by apps as X-AOBS-Project
    description: Mapped[str] = mapped_column(Text, default="")
    rules: Mapped[list] = mapped_column(JSON, default=list)
    mode: Mapped[str] = mapped_column(String(20), default="monitor")  # monitor | block | repair
    max_repairs: Mapped[int] = mapped_column(Integer, default=1)
    fallback_models: Mapped[list] = mapped_column(JSON, default=list)  # same-provider models, in order
    judge_in_enforcement: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class LLMCall(Base):
    __tablename__ = "llm_calls"
    __table_args__ = (
        Index("ix_llm_ws_created", "workspace_id", "created_at"),
        Index("ix_llm_ws_model_created", "workspace_id", "model", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    provider: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(120), default="")
    endpoint: Mapped[str] = mapped_column(String(200), default="")
    contract_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    credential_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="gateway")  # gateway | drift_test
    session_id: Mapped[str] = mapped_column(String(200), default="")
    end_user: Mapped[str] = mapped_column(String(200), default="")
    tags: Mapped[list] = mapped_column(JSON, default=list)

    status_code: Mapped[int] = mapped_column(Integer, default=200)
    error: Mapped[str] = mapped_column(Text, default="")
    streamed: Mapped[bool] = mapped_column(Boolean, default=False)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    ttft_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    system_prompt: Mapped[str] = mapped_column(Text, default="")
    last_user: Mapped[str] = mapped_column(Text, default="")
    n_messages: Mapped[int] = mapped_column(Integer, default=0)
    response_text: Mapped[str] = mapped_column(Text, default="")
    content_stored: Mapped[bool] = mapped_column(Boolean, default=True)
    finish_reason: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    usage_estimated: Mapped[bool] = mapped_column(Boolean, default=False)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)

    # Evaluation
    eval_status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | done | error
    checks: Mapped[list] = mapped_column(JSON, default=list)
    violations: Mapped[int] = mapped_column(Integer, default=0)
    adherence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    judge_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    judge_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    relevance: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pii_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    injection_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    severity: Mapped[str] = mapped_column(String(20), default="ok", index=True)  # ok | warning | critical

    # Enforcement
    enforcement_action: Mapped[str] = mapped_column(String(20), default="none")  # none|passed|repaired|fallback|blocked
    attempts: Mapped[list] = mapped_column(JSON, default=list)


WINDOW_METRICS = ("violation_rate", "error_rate", "p95_latency_ms", "avg_judge_score", "avg_adherence", "cost_usd")
EVENT_METRICS = ("event_pii", "event_injection", "event_blocked", "event_critical", "event_drift_failed")


class AlertRule(Base):
    __tablename__ = "alert_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    metric: Mapped[str] = mapped_column(String(40))  # WINDOW_METRICS or EVENT_METRICS
    comparison: Mapped[str] = mapped_column(String(4), default=">")  # > or <
    threshold: Mapped[float] = mapped_column(Float, default=0.0)
    window_minutes: Mapped[int] = mapped_column(Integer, default=60)
    min_calls: Mapped[int] = mapped_column(Integer, default=10)
    scope: Mapped[dict] = mapped_column(JSON, default=dict)  # {"provider", "model", "contract_id"}
    channels: Mapped[dict] = mapped_column(JSON, default=dict)  # {"email": [...], "slack": url, "webhook": url}
    cooldown_minutes: Mapped[int] = mapped_column(Integer, default=30)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_fired_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class AlertEvent(Base):
    __tablename__ = "alert_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    rule_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(300))
    message: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[str] = mapped_column(String(20), default="warning")
    value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ref_type: Mapped[str] = mapped_column(String(20), default="")  # llm_call | drift_test | window
    ref_id: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | acknowledged | resolved
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    notified: Mapped[list] = mapped_column(JSON, default=list)  # delivery result per channel


class DriftTest(Base):
    """A fixed prompt run on a schedule to detect provider-side changes in behavior."""

    __tablename__ = "drift_tests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    provider: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(120))
    credential_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    prompt: Mapped[str] = mapped_column(Text)
    contract_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    baseline_text: Mapped[str] = mapped_column(Text, default="")
    similarity_threshold: Mapped[float] = mapped_column(Float, default=0.5)
    interval_minutes: Mapped[int] = mapped_column(Integer, default=360)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_status: Mapped[str] = mapped_column(String(20), default="never")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class DriftRun(Base):
    __tablename__ = "drift_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    test_id: Mapped[int] = mapped_column(ForeignKey("drift_tests.id", ondelete="CASCADE"), index=True)
    ran_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    status: Mapped[str] = mapped_column(String(20))  # baseline | pass | fail | error
    similarity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    violations: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    response_text: Mapped[str] = mapped_column(Text, default="")
    detail: Mapped[str] = mapped_column(Text, default="")
