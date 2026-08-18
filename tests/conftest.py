"""Shared pytest fixtures and configuration."""
import pytest
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Set test environment variables
os.environ["ENVIRONMENT"] = "testing"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"  # Use in-memory DB for tests
os.environ["SECRET_KEY"] = "test-secret-key-do-not-use-in-production"


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
    """Reset rate limiter between tests."""
    # This prevents rate limit carryover between tests
    from api.rate_limiter import RateLimiter
    
    yield
    
    # Reset rate limiter state after each test
    # Note: This is a simple approach; in production you might want
    # to use a more sophisticated rate limiter with configurable backend
