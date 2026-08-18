"""Shared pytest fixtures and configuration."""
import pytest
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Set test environment variables - use file-based SQLite for thread safety
os.environ["ENVIRONMENT"] = "testing"
os.environ["DATABASE_URL"] = "sqlite:///./test_database.db?check_same_thread=false"
os.environ["SECRET_KEY"] = "test-secret-key-do-not-use-in-production"


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """Create test database tables before all tests."""
    from api.database import init_db, drop_all
    
    # Drop any existing tables
    try:
        drop_all()
    except:
        pass
    
    # Create fresh tables
    init_db()
    
    yield
    
    # Cleanup after all tests
    try:
        drop_all()
    except:
        pass
    
    # Remove test database file
    test_db_path = Path("test_database.db")
    if test_db_path.exists():
        test_db_path.unlink()


@pytest.fixture(scope="function", autouse=True)
def clean_database():
    """Clean database between tests."""
    from api.database import SessionLocal, TraceRecord, FeedbackRecord
    
    yield
    
    # Clean up data after each test
    db = SessionLocal()
    try:
        db.query(TraceRecord).delete()
        db.query(FeedbackRecord).delete()
        db.commit()
    except:
        db.rollback()
    finally:
        db.close()


@pytest.fixture(scope="session")
def test_data_dir():
    """Get test data directory."""
    return Path(__file__).parent / "test_data"


@pytest.fixture(scope="session")
def sample_trace_json():
    """Sample trace JSON for testing."""
    return {
        "task_description": "Search for weather and summarize",
        "steps": [
            {
                "step_id": 0,
                "action_type": "tool_call",
                "tool_name": "search",
                "arguments": {"query": "weather Seattle"},
                "output": "Temperature: 65F, Condition: Sunny",
                "latency_ms": 120,
                "tokens_used": 50
            },
            {
                "step_id": 1,
                "action_type": "tool_call",
                "tool_name": "summarize",
                "arguments": {"text": "Temperature: 65F, Condition: Sunny"},
                "output": "It's 65 degrees and sunny in Seattle.",
                "latency_ms": 80,
                "tokens_used": 30
            }
        ]
    }


@pytest.fixture(scope="session")
def anomalous_trace_json():
    """Anomalous trace with repetitive tool calls."""
    return {
        "task_description": "Stuck in a loop",
        "steps": [
            {
                "step_id": i,
                "action_type": "tool_call",
                "tool_name": "search",
                "arguments": {"query": "same query"},
                "output": "Error: Not found",
                "latency_ms": 100,
                "tokens_used": 10
            }
            for i in range(20)  # Repetitive steps
        ]
    }


@pytest.fixture
def valid_api_key():
    """Return a valid API key for testing."""
    return "dev-key-12345"


@pytest.fixture
def invalid_api_key():
    """Return an invalid API key for testing."""
    return "invalid-key-xyz"


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Reset rate limiter state before each test."""
    # Import here to avoid circular imports
    from api.main import rate_limiter
    
    # Clear the rate limiter buckets before each test
    rate_limiter.buckets.clear()
    rate_limiter.request_counts.clear()
    
    yield
    
    # Clear again after test
    rate_limiter.buckets.clear()
    rate_limiter.request_counts.clear()
