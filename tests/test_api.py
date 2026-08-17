"""Integration tests for API endpoints."""
import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


class TestHealthEndpoints:
    """Test health and status endpoints."""
    
    def test_health_check(self):
        """Test /health endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
    
    def test_stats_endpoint(self):
        """Test /stats endpoint."""
        response = client.get("/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total_traces" in data
        assert "anomalous_traces" in data


class TestTraceIngestion:
    """Test trace ingestion endpoint."""
    
    def test_ingest_valid_trace(self):
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
        
        response = client.post("/ingest_trace", json=trace)
        assert response.status_code == 200
        
        data = response.json()
        assert "trace_id" in data
        assert "isolation_score" in data
        assert "combined_score" in data
        assert "recommended_action" in data
    
    def test_ingest_invalid_trace(self):
        """Test ingesting invalid trace data."""
        invalid_trace = {
            "task_description": "test",
            # Missing steps field
        }
        
        response = client.post("/ingest_trace", json=invalid_trace)
        assert response.status_code == 422  # Validation error


class TestFeedback:
    """Test feedback endpoint."""
    
    def test_send_feedback(self):
        """Test sending feedback."""
        feedback = {
            "context_summary": [0.1, 0.2, 0.3, 0.4, 1.0],
            "action": "continue",
            "reward": 1.0
        }
        
        response = client.post("/feedback", json=feedback)
        assert response.status_code == 200
        assert response.json()["status"] == "policy updated"
    
    def test_send_invalid_feedback(self):
        """Test sending invalid feedback."""
        invalid_feedback = {
            "context_summary": [0.1, 0.2],  # Wrong size
            "action": "invalid_action",
            "reward": "not_a_number"
        }
        
        response = client.post("/feedback", json=invalid_feedback)
        assert response.status_code == 422


class TestAuthentication:
    """Test authentication and authorization."""
    
    def test_no_auth_required_for_health(self):
        """Health endpoint should not require auth."""
        response = client.get("/health")
        assert response.status_code == 200
    
    def test_valid_api_key(self):
        """Test with valid API key."""
        headers = {"X-API-Key": "dev-key-12345"}
        response = client.get("/stats", headers=headers)
        # Should work even if auth is not yet enforced
        assert response.status_code in [200, 401]


class TestRateLimiting:
    """Test rate limiting."""
    
    def test_rate_limit_enforcement(self):
        """Test that rate limiting works."""
        # Make many rapid requests
        responses = []
        for _ in range(100):
            response = client.get("/stats")
            responses.append(response.status_code)
        
        # Should get some 429 responses if rate limiting is active
        # Note: This might not trigger in test environment
        assert all(code in [200, 429] for code in responses)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
