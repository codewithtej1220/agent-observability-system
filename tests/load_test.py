"""Load testing with Locust.

Run with: locust -f tests/load_test.py --host http://localhost:8000
"""
from locust import HttpUser, task, between
import json
import random


class AgentObservabilityUser(HttpUser):
    """Simulated user for load testing."""
    
    wait_time = between(1, 3)  # Wait 1-3 seconds between tasks
    
    def on_start(self):
        """Called when a simulated user starts."""
        # Check if API is available
        self.client.get("/health")
    
    @task(10)
    def ingest_normal_trace(self):
        """Ingest a normal trace (most common)."""
        trace = {
            "task_description": f"Normal task {random.randint(1, 1000)}",
            "steps": [
                {
                    "step_id": i,
                    "action_type": "tool_call",
                    "tool_name": random.choice(["search", "calculator", "read_file"]),
                    "arguments": {"input": f"arg_{i}"},
                    "output": f"output_{i}",
                    "latency_ms": random.randint(50, 200),
                    "tokens_used": random.randint(10, 50)
                }
                for i in range(random.randint(2, 5))
            ]
        }
        
        self.client.post("/ingest_trace", json=trace)
    
    @task(3)
    def ingest_anomalous_trace(self):
        """Ingest an anomalous trace (less common)."""
        # Looping trace
        trace = {
            "task_description": f"Anomalous task {random.randint(1, 1000)}",
            "steps": [
                {
                    "step_id": i,
                    "action_type": "tool_call",
                    "tool_name": "search",
                    "arguments": {"query": "same query"},
                    "output": "Error",
                    "latency_ms": 100,
                    "tokens_used": 10
                }
                for i in range(15)  # Repetitive
            ]
        }
        
        response = self.client.post("/ingest_trace", json=trace)
        
        if response.status_code == 200:
            result = response.json()
            
            # Send feedback
            feedback = {
                "context_summary": result["context_summary"],
                "action": result["recommended_action"],
                "reward": 1.0 if result["is_anomalous"] else -0.5
            }
            self.client.post("/feedback", json=feedback)
    
    @task(5)
    def get_stats(self):
        """Get system statistics."""
        self.client.get("/stats")
    
    @task(2)
    def get_traces(self):
        """Get recent traces."""
        self.client.get("/traces?limit=10")
    
    @task(1)
    def health_check(self):
        """Health check endpoint."""
        self.client.get("/health")


# Test scenarios for different loads
class LightLoadUser(AgentObservabilityUser):
    """Light load: 10-50 users."""
    wait_time = between(3, 5)


class MediumLoadUser(AgentObservabilityUser):
    """Medium load: 50-200 users."""
    wait_time = between(1, 3)


class HeavyLoadUser(AgentObservabilityUser):
    """Heavy load: 200+ users."""
    wait_time = between(0.5, 1.5)
