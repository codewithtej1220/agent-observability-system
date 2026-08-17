"""Unit tests for ML models."""
import numpy as np
import pytest

from agent_harness.trace_schema import Trace, Step
from anomaly_model.model import AnomalyDetector
from embedding_pipeline.embedder import TraceEmbedder
from rl_policy.bandit import LinUCBBandit, compute_reward


class TestAnomalyDetector:
    """Test anomaly detection model."""
    
    def test_detector_training(self):
        """Test detector can be trained."""
        # Create dummy embeddings
        embeddings = np.random.randn(100, 50)
        
        detector = AnomalyDetector(contamination=0.1)
        detector.fit(embeddings)
        
        assert detector._fitted is True
    
    def test_detector_scoring(self):
        """Test detector can score embeddings."""
        embeddings = np.random.randn(100, 50)
        test_embeddings = np.random.randn(10, 50)
        
        detector = AnomalyDetector(contamination=0.1)
        detector.fit(embeddings)
        
        scores = detector.score(test_embeddings)
        
        assert len(scores) == 10
        for score in scores:
            assert 0 <= score.isolation_score <= 1
            assert 0 <= score.combined_score <= 1
            assert isinstance(score.is_anomalous, bool)


class TestTraceEmbedder:
    """Test trace embedding."""
    
    def test_embedder_fit_transform(self):
        """Test embedder can fit and transform traces."""
        # Create sample traces
        traces = [
            Trace(
                trace_id=f"trace_{i}",
                task_description=f"task {i}",
                steps=[
                    Step(
                        step_id=0,
                        action_type="tool_call",
                        tool_name="search",
                        arguments={"query": "test"},
                        output="result",
                        latency_ms=100,
                        tokens_used=10
                    )
                ]
            )
            for i in range(20)
        ]
        
        embedder = TraceEmbedder()
        embeddings = embedder.fit_transform(traces)
        
        assert embeddings.shape[0] == 20
        assert embeddings.shape[1] > 0
    
    def test_embedder_transform_single(self):
        """Test embedder can transform a single trace."""
        traces = [
            Trace(
                trace_id="trace_1",
                task_description="task",
                steps=[
                    Step(
                        step_id=0,
                        action_type="tool_call",
                        tool_name="search",
                        arguments={},
                        output="",
                        latency_ms=0,
                        tokens_used=0
                    )
                ]
            )
        ]
        
        embedder = TraceEmbedder()
        embeddings = embedder.fit_transform(traces)
        
        # Transform same trace
        new_embedding = embedder.transform(traces)
        
        assert new_embedding.shape == embeddings.shape


class TestLinUCBBandit:
    """Test reinforcement learning bandit."""
    
    def test_bandit_initialization(self):
        """Test bandit initializes correctly."""
        bandit = LinUCBBandit(n_features=5)
        
        assert len(bandit.actions) == 4
        assert bandit.n_features == 5
    
    def test_bandit_select_action(self):
        """Test bandit can select actions."""
        bandit = LinUCBBandit(n_features=5)
        context = np.array([0.1, 0.2, 0.3, 0.4, 1.0])
        
        action = bandit.select_action(context)
        
        assert action in ["continue", "retry_step", "interrupt_human", "escalate_model"]
    
    def test_bandit_update(self):
        """Test bandit can update from feedback."""
        bandit = LinUCBBandit(n_features=5)
        context = np.array([0.1, 0.2, 0.3, 0.4, 1.0])
        
        # Initial state
        initial_A = bandit._A["continue"].copy()
        initial_b = bandit._b["continue"].copy()
        
        # Update
        bandit.update(context, "continue", reward=1.0)
        
        # Check state changed
        assert not np.array_equal(bandit._A["continue"], initial_A)
        assert not np.array_equal(bandit._b["continue"], initial_b)
    
    def test_compute_reward(self):
        """Test reward computation."""
        # Success case
        reward = compute_reward("success", "continue", steps_saved=0, cost_saved=0.0)
        assert reward > 0
        
        # Failure case
        reward = compute_reward("failure", "continue", steps_saved=0, cost_saved=0.0)
        assert reward < 0
        
        # With savings
        reward = compute_reward("success", "interrupt_human", steps_saved=5, cost_saved=1.0)
        assert reward > 1.0  # Base + savings - penalty


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
