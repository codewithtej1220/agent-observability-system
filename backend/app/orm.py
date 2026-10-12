"""Database tables."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ============================================================================
# Accounts, workspaces and credentials
# ============================================================================

DEFAULT_WORKSPACE_SETTINGS = {
    "store_content": True,       # store prompt/response text for LLM calls
    "redact_pii": False,         # mask emails/phones/cards before storing
    "retention_days": 30,        # delete LLM call content older than this
    "auto_judge": False,         # judge every call against its system prompt
    "judge_sample_rate": 0.25,   # fraction of calls auto-judged (cost control)
    "judge_credential_id": None, # provider credential used by the LLM judge
    "judge_model": None,         # e.g. "gpt-4o-mini", "claude-haiku-4-5", "gemini-2.5-flash"
}


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    google_sub: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200))
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    def setting(self, key: str):
        return (self.settings or {}).get(key, DEFAULT_WORKSPACE_SETTINGS.get(key))


ROLES = ("admin", "member", "viewer")


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "workspace_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20), default="member")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class UserSession(Base):
    """Server-side session; the cookie holds a random token, the DB holds its SHA-256."""

    __tablename__ = "sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    workspace_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    user_agent: Mapped[str] = mapped_column(String(300), default="")


class ApiKey(Base):
    """Workspace API key for the SDK and the LLM gateway. Only its SHA-256 is stored."""

    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    prefix: Mapped[str] = mapped_column(String(16))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_by: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


PROVIDERS = ("openai", "anthropic", "gemini")


class ProviderCredential(Base):
    """An LLM provider API key, encrypted at rest (see app/crypto.py)."""

    __tablename__ = "provider_credentials"
    __table_args__ = (UniqueConstraint("workspace_id", "provider", "name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(100), default="default")
    encrypted_key: Mapped[str] = mapped_column(Text)
    key_hint: Mapped[str] = mapped_column(String(16))
    is_default: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


# ============================================================================
# Agent monitoring
# ============================================================================

class Agent(Base):
    __tablename__ = "agents"

    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    model: Mapped[str] = mapped_column(String(100), default="")
    framework: Mapped[str] = mapped_column(String(100), default="")
    registered_tools: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class RunRecord(Base):
    __tablename__ = "runs"
    __table_args__ = (
        Index("ix_runs_ws_agent_started", "workspace_id", "agent_id", "started_at"),
        Index("ix_runs_ws_severity_started", "workspace_id", "severity", "started_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    agent_id: Mapped[str] = mapped_column(String(64), index=True)
    task: Mapped[str] = mapped_column(Text, default="")
    model: Mapped[str] = mapped_column(String(100), default="")
    status: Mapped[str] = mapped_column(String(20), default="running")  # running | completed | incomplete
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    n_steps: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    has_final_answer: Mapped[bool] = mapped_column(Boolean, default=False)

    # Assessment
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    severity: Mapped[str] = mapped_column(String(20), default="healthy")
    failure_type: Mapped[Optional[str]] = mapped_column(String(40), nullable=True, index=True)
    probabilities: Mapped[dict] = mapped_column(JSON, default=dict)
    signals: Mapped[list] = mapped_column(JSON, default=list)
    features: Mapped[dict] = mapped_column(JSON, default=dict)
    rule_severity: Mapped[float] = mapped_column(Float, default=0.0)
    novelty_score: Mapped[float] = mapped_column(Float, default=0.0)
    open_set_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    cluster_id: Mapped[int] = mapped_column(Integer, default=-1)
    coords: Mapped[list] = mapped_column(JSON, default=list)
    risk_trajectory: Mapped[list] = mapped_column(JSON, default=list)
    first_flag_step: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    avoidable_tokens: Mapped[int] = mapped_column(Integer, default=0)
    model_version: Mapped[str] = mapped_column(String(20), default="")

    # Intervention
    recommended_action: Mapped[str] = mapped_column(String(40), default="continue")
    decision: Mapped[dict] = mapped_column(JSON, default=dict)
    policy_context: Mapped[list] = mapped_column(JSON, default=list)

    # Ground truth when traffic comes from the simulator (never shown to models).
    source_label: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    failure_onset: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    steps: Mapped[List["StepRecord"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="StepRecord.idx"
    )
    feedback: Mapped[List["Feedback"]] = relationship(back_populates="run", cascade="all, delete-orphan")

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class StepRecord(Base):
    __tablename__ = "steps"
    __table_args__ = (Index("ix_steps_run_idx", "run_id", "idx"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    idx: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(20))
    tool_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    arguments: Mapped[dict] = mapped_column(JSON, default=dict)
    output: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(10), default="ok")
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    timestamp: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    run: Mapped[RunRecord] = relationship(back_populates="steps")


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(40))  # true condition: healthy or a failure type
    action_taken: Mapped[str] = mapped_column(String(40))
    resolved: Mapped[bool] = mapped_column(Boolean)
    reward: Mapped[float] = mapped_column(Float)
    notes: Mapped[str] = mapped_column(Text, default="")
    reviewer: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    used_in_version: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    run: Mapped[RunRecord] = relationship(back_populates="feedback")


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version: Mapped[str] = mapped_column(String(20), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    trigger: Mapped[str] = mapped_column(String(40), default="bootstrap")
    n_train_runs: Mapped[int] = mapped_column(Integer, default=0)
    n_human_labels: Mapped[int] = mapped_column(Integer, default=0)
    macro_f1: Mapped[float] = mapped_column(Float, default=0.0)
    pr_auc: Mapped[float] = mapped_column(Float, default=0.0)
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="")


class PolicyEvent(Base):
    """One policy decision, and later its reward once the outcome is known."""

    __tablename__ = "policy_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(Integer, index=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(40))
    failure_type: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    risk_score: Mapped[float] = mapped_column(Float)
    reward: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    rewarded_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
