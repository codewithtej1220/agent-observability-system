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
    # Deterministic corrections tried before asking the model to repair (enforcing modes only).
    auto_redact: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    auto_fix_json: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class LLMCall(Base):
    __tablename__ = "llm_calls"
    __table_args__ = (
        Index("ix_llm_ws_created", "workspace_id", "created_at"),
        Index("ix_llm_ws_model_created", "workspace_id", "model", "created_at"),
        Index("ix_llm_ws_session", "workspace_id", "session_id"),
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
    # Trace linking (X-AOBS-Run / X-AOBS-Step) and prompt version (X-AOBS-Prompt: name@version)
    run_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    run_step: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    prompt_name: Mapped[str] = mapped_column(String(120), default="", server_default="")
    prompt_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

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


FEEDBACK_VERDICTS = ("correct", "false_positive", "missed")


class CallFeedback(Base):
    """A reviewer's verdict on a call's flags; used to measure each check's real precision."""

    __tablename__ = "call_feedback"
    __table_args__ = (UniqueConstraint("call_id", "user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    call_id: Mapped[str] = mapped_column(ForeignKey("llm_calls.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(Integer)
    verdict: Mapped[str] = mapped_column(String(20))  # correct | false_positive | missed
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Prompt(Base):
    """One version of a managed prompt. Versions are immutable; labels (e.g. "production") move between them."""

    __tablename__ = "prompts"
    __table_args__ = (UniqueConstraint("workspace_id", "name", "version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    version: Mapped[int] = mapped_column(Integer)
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    template: Mapped[str] = mapped_column(Text, default="")  # user message; {{variables}} filled by the app
    model: Mapped[str] = mapped_column(String(120), default="")
    config: Mapped[dict] = mapped_column(JSON, default=dict)  # e.g. temperature, max_tokens
    labels: Mapped[list] = mapped_column(JSON, default=list)
    commit_message: Mapped[str] = mapped_column(String(500), default="")
    created_by: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Dataset(Base):
    __tablename__ = "datasets"
    __table_args__ = (UniqueConstraint("workspace_id", "name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class DatasetItem(Base):
    __tablename__ = "dataset_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), index=True)
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    input: Mapped[str] = mapped_column(Text)
    expected: Mapped[str] = mapped_column(Text, default="")
    source_call_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Experiment(Base):
    """One run of a dataset against a model (and optionally a prompt version), scored by a contract."""

    __tablename__ = "experiments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    provider: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(120))
    credential_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    prompt_name: Mapped[str] = mapped_column(String(120), default="")
    prompt_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    contract_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="running")  # running | done | error
    detail: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class ExperimentResult(Base):
    __tablename__ = "experiment_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    experiment_id: Mapped[int] = mapped_column(ForeignKey("experiments.id", ondelete="CASCADE"), index=True)
    item_id: Mapped[int] = mapped_column(Integer)
    call_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(10), default="ok")  # ok | error
    output: Mapped[str] = mapped_column(Text, default="")
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    violations: Mapped[int] = mapped_column(Integer, default=0)
    similarity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # vs. expected, when given
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    detail: Mapped[str] = mapped_column(Text, default="")
