"""PostgreSQL database configuration with SQLAlchemy ORM."""
import os
from contextlib import contextmanager

from dotenv import load_dotenv
from sqlalchemy import Column, Float, Integer, String, Boolean, JSON, DateTime, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import func

# Load environment variables from .env file
load_dotenv()

# Database URL from environment (Supabase PostgreSQL)
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL not found in environment variables!\n"
        "Create a .env file with: DATABASE_URL=postgresql://..."
    )

# Create engine
# SQLite doesn't support pool_size and max_overflow, so only use them for PostgreSQL
if DATABASE_URL.startswith("postgresql"):
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,  # Check connection health
        pool_size=10,  # Connection pool
        max_overflow=20,
        echo=False  # Set to True for SQL debugging
    )
else:
    # SQLite (for testing)
    engine = create_engine(
        DATABASE_URL,
        echo=False  # Set to True for SQL debugging
    )

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()


# ============================================================================
# MODELS
# ============================================================================

class TraceRecord(Base):
    """Database model for agent traces."""
    __tablename__ = "traces"
    
    id = Column(Integer, primary_key=True, index=True)
    trace_id = Column(String, unique=True, index=True, nullable=False)
    task_description = Column(String, nullable=False)
    trace_json = Column(JSON, nullable=False)
    
    # Anomaly detection results
    isolation_score = Column(Float)
    is_cluster_outlier = Column(Boolean)
    combined_score = Column(Float, index=True)
    is_anomalous = Column(Boolean, index=True)
    
    # RL policy decision
    policy_action = Column(String)
    context_summary = Column(JSON)
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class FeedbackRecord(Base):
    """Database model for feedback signals."""
    __tablename__ = "feedback"
    
    id = Column(Integer, primary_key=True, index=True)
    trace_id = Column(String, index=True)
    action = Column(String, nullable=False)
    reward = Column(Float, nullable=False)
    outcome = Column(String)  # success/failure
    
    # Context at time of feedback
    context_summary = Column(JSON)
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ============================================================================
# DATABASE OPERATIONS
# ============================================================================

def get_db():
    """Dependency for FastAPI to get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_context():
    """Context manager for database session."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db():
    """Initialize database tables."""
    Base.metadata.create_all(bind=engine)
    print("✅ Database tables created")


def drop_all():
    """Drop all tables (use with caution!)."""
    Base.metadata.drop_all(bind=engine)
    print("⚠️ All tables dropped")


if __name__ == "__main__":
    # Create tables
    init_db()
