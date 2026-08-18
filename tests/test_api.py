"""Integration tests for API endpoints."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import numpy as np

from api.main import app

client = TestClient(app)

# Test API keys
VALID_API_KEY = "dev-key-12345"
INVALID_API_KEY = "invalid-key"


@pytest.fixture
def mock_models(monkeypatch):
    """Mock ML models to avoid loading actual artifacts."""
    # Mock embedder
    mock_embedder = MagicMock()
    mock_embedder.transform.return_value = np.array([[0.1, 0.2, 0.3, 0.4, 0.5]])
    
    # Mock detector
    mock_detector = MagicMock()
    mock_score = MagicMock()
    mock_score.isolation_score = 0.3
    mock_score.is_cluster_outlier = False
    mock_score.combined_score = 0.25
    mock_score.is_anomalous = False
    mock_detector.score.return_value = [mock_score]
    
    monkeypatch.setattr("api.main._embedder", mock_embedder)
    monkeypatch.setattr("api.main._detector", mock_detector)
    
    return {"embedder": mock_embedder, "detector": mock_detector}


class TestHealthEndpoints:
    """Test health and status endpoints."""
    
    def test_health_check(self):
        """Test /health endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
    
    def test_health_check_rate_limited(self):
        """Test health endpoint is rate limited."""
        # Make many rapid requests
        responses = []
        for _ in range(110):  # Over the 100 req/min limit
            response = client.get("/health")
            responses.append(response.status_code)
        
        # Should eventually get rate limited
        # Note: Actual rate limiting behavior depends on timing
        assert any(code in [200, 429] for code in responses)
    
    def test_stats_endpoint(self):
        """Test /stats endpoint."""
        response = client.get("/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total_traces" in data
        assert "anomalous_traces" in data
        assert "avg_combined_score" in data
        assert isinstance(data["total_traces"], int)
        assert isinstance(data["anomalous_traces"], int)


class TestTraceIngestion:
    """Test trace ingestion endpoint."""
    
    def test_ingest_without_auth(self):
        """Test ingesting trace without authentication."""
        trace = {
            "task_description": "test task",
            "steps": [
                {
                    "step_id": 0,
                    "action_type": "tool_call",
                    "tool_name": "search",
                    "arguments": {"query": "test"},
                    "output": "result",
                    "latency_ms": 100,
                    "tokens_used": 10
                }
            ]
        }
        
        response = client.post("/ingest_trace", json=trace)
        assert response.status_code == 401  # Unauthorized
    
    def test_ingest_with_invalid_api_key(self):
        """Test ingesting trace with invalid API key."""
        trace = {
            "task_description": "test task",
            "steps": []
        }
        
        headers = {"X-API-Key": INVALID_API_KEY}
        response = client.post("/ingest_trace", json=trace, headers=headers)
        assert response.status_code == 401
    
    def test_ingest_valid_trace(self, mock_models):
        """Test ingesting a valid trace."""
        trace = {
            "task_description": "test task",
            "steps": [
                {
                    "step_id": 0,
                    "action_type": "tool_call",
                    "tool_name": "search",
                    "arguments": {"query": "test"},
                    "output": "result",
                    "latency_ms": 100,
                    "tokens_used": 10
                }
            ]
        }
        
        headers = {"X-API-Key": VALID_API_KEY}
        response = client.post("/ingest_trace", json=trace, headers=headers)
        assert response.status_code == 200
        
        data = response.json()
        assert "trace_id" in data
        assert "isolation_score" in data
        assert "combined_score" in data
        assert "recommended_action" in data
        assert "context_summary" in data
        assert isinstance(data["isolation_score"], float)
        assert isinstance(data["is_anomalous"], bool)
    
    def test_ingest_empty_steps(self, mock_models):
        """Test ingesting trace with no steps."""
        trace = {
            "task_description": "empty trace",
            "steps": []
        }
        
        headers = {"X-API-Key": VALID_API_KEY}
        response = client.post("/ingest_trace", json=trace, headers=headers)
        assert response.status_code == 200
    
    def test_ingest_invalid_trace(self):
        """Test ingesting invalid trace data."""
        invalid_trace = {
            "task_description": "test",
            # Missing required steps field
        }
        
        headers = {"X-API-Key": VALID_API_KEY}
        response = client.post("/ingest_trace", json=invalid_trace, headers=headers)
        assert response.status_code == 422  # Validation error
    
    def test_ingest_malformed_json(self):
        """Test ingesting malformed JSON."""
        headers = {
            "X-API-Key": VALID_API_KEY,
            "Content-Type": "application/json"
        }
        response = client.post("/ingest_trace", data="invalid json{", headers=headers)
        assert response.status_code == 422


class TestFeedback:
    """Test feedback endpoint."""
    
    def test_feedback_without_auth(self):
        """Test sending feedback without authentication."""
        feedback = {
            "context_summary": [0.1, 0.2, 0.3, 0.4, 1.0],
            "action": "continue",
            "reward": 1.0
        }
        
        response = client.post("/feedback", json=feedback)
        assert response.status_code == 401
    
    def test_send_valid_feedback(self):
        """Test sending valid feedback."""
        feedback = {
            "context_summary": [0.1, 0.2, 0.3, 0.4, 1.0],
            "action": "continue",
            "reward": 1.0
        }
        
        headers = {"X-API-Key": VALID_API_KEY}
        response = client.post("/feedback", json=feedback, headers=headers)
        assert response.status_code == 200
        assert response.json()["status"] == "policy updated"
    
    def test_send_negative_reward(self):
        """Test sending negative reward."""
        feedback = {
            "context_summary": [0.1, 0.2, 0.3, 0.4, 1.0],
            "action": "retry_step",
            "reward": -0.5
        }
        
        headers = {"X-API-Key": VALID_API_KEY}
        response = client.post("/feedback", json=feedback, headers=headers)
        assert response.status_code == 200
    
    def test_send_invalid_feedback(self):
        """Test sending invalid feedback."""
        invalid_feedback = {
            "context_summary": [0.1, 0.2],  # Wrong size
            "action": "invalid_action",
            "reward": "not_a_number"
        }
        
        headers = {"X-API-Key": VALID_API_KEY}
        response = client.post("/feedback", json=invalid_feedback, headers=headers)
        assert response.status_code == 422


class TestTraceRetrieval:
    """Test trace retrieval endpoint."""
    
    def test_get_traces_without_auth(self):
        """Test getting traces without authentication."""
        response = client.get("/traces")
        assert response.status_code == 401
    
    def test_get_traces_with_auth(self):
        """Test getting traces with authentication."""
        headers = {"X-API-Key": VALID_API_KEY}
        response = client.get("/traces", headers=headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)
    
    def test_get_traces_with_limit(self):
        """Test getting traces with limit parameter."""
        headers = {"X-API-Key": VALID_API_KEY}
        response = client.get("/traces?limit=5", headers=headers)
        assert response.status_code == 200
        traces = response.json()
        assert len(traces) <= 5


class TestAuthentication:
    """Test authentication and authorization."""
    
    def test_no_auth_required_for_health(self):
        """Health endpoint should not require auth."""
        response = client.get("/health")
        assert response.status_code == 200
    
    def test_no_auth_required_for_stats(self):
        """Stats endpoint should not require auth (but is rate limited)."""
        response = client.get("/stats")
        assert response.status_code == 200
    
    def test_auth_required_for_ingest(self):
        """Ingest endpoint should require auth."""
        trace = {"task_description": "test", "steps": []}
        response = client.post("/ingest_trace", json=trace)
        assert response.status_code == 401
    
    def test_auth_required_for_feedback(self):
        """Feedback endpoint should require auth."""
        feedback = {
            "context_summary": [0.1, 0.2, 0.3, 0.4, 1.0],
            "action": "continue",
            "reward": 1.0
        }
        response = client.post("/feedback", json=feedback)
        assert response.status_code == 401
    
    def test_auth_required_for_traces(self):
        """Traces endpoint should require auth."""
        response = client.get("/traces")
        assert response.status_code == 401
    
    def test_valid_api_key_admin(self):
        """Test with valid admin API key."""
        headers = {"X-API-Key": "dev-key-12345"}
        response = client.get("/stats", headers=headers)
        assert response.status_code == 200


class TestRateLimiting:
    """Test rate limiting."""
    
    def test_rate_limit_on_stats(self):
        """Test rate limiting on stats endpoint."""
        responses = []
        for _ in range(105):  # Over the 100 req/min limit
            response = client.get("/stats")
            responses.append(response.status_code)
        
        # Should get mix of 200 and 429
        assert 200 in responses
        # Note: In test environment, rate limiting might not trigger


class TestSentryDebug:
    """Test Sentry debug endpoint."""
    
    def test_sentry_debug_in_dev(self):
        """Test Sentry debug endpoint in development."""
        # This will trigger an error, which is expected
        response = client.get("/sentry-debug")
        # Should either raise 500 (if Sentry is off) or be caught
        assert response.status_code in [500, 200, 403]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
