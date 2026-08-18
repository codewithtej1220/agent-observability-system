"""Unit tests for database operations."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from api.database import Base, TraceRecord, FeedbackRecord
import json


# Use in-memory SQLite for testing
TEST_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture
def test_db():
    """Create a test database."""
    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.create_all(bind=engine)
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestSessionLocal()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


class TestTraceRecord:
    """Test TraceRecord model."""
    
    def test_create_trace_record(self, test_db):
        """Test creating a trace record."""
        trace = TraceRecord(
            trace_id="test-123",
            task_description="Test task",
            trace_json={"steps": []},
            isolation_score=0.3,
            is_cluster_outlier=False,
            combined_score=0.25,
            is_anomalous=False,
            policy_action="continue",
            context_summary=[0.1, 0.2, 0.3, 0.4, 1.0]
        )
        
        test_db.add(trace)
        test_db.commit()
        test_db.refresh(trace)
        
        assert trace.id is not None
        assert trace.trace_id == "test-123"
        assert trace.created_at is not None
    
    def test_trace_record_unique_constraint(self, test_db):
        """Test that trace_id is unique."""
        trace1 = TraceRecord(
            trace_id="duplicate-id",
            task_description="Task 1",
            trace_json={"steps": []},
            combined_score=0.5,
            is_anomalous=False
        )
        test_db.add(trace1)
        test_db.commit()
        
        # Try to add another with same trace_id
        trace2 = TraceRecord(
            trace_id="duplicate-id",
            task_description="Task 2",
            trace_json={"steps": []},
            combined_score=0.6,
            is_anomalous=True
        )
        test_db.add(trace2)
        
        with pytest.raises(Exception):  # Should raise IntegrityError
            test_db.commit()
    
    def test_query_traces_by_anomaly(self, test_db):
        """Test querying traces by anomaly status."""
        # Add anomalous trace
        trace1 = TraceRecord(
            trace_id="anomalous-1",
            task_description="Bad task",
            trace_json={"steps": []},
            combined_score=0.8,
            is_anomalous=True
        )
        
        # Add normal trace
        trace2 = TraceRecord(
            trace_id="normal-1",
            task_description="Good task",
            trace_json={"steps": []},
            combined_score=0.2,
            is_anomalous=False
        )
        
        test_db.add_all([trace1, trace2])
        test_db.commit()
        
        # Query anomalous traces
        anomalous = test_db.query(TraceRecord).filter(
            TraceRecord.is_anomalous == True
        ).all()
        
        assert len(anomalous) == 1
        assert anomalous[0].trace_id == "anomalous-1"
    
    def test_query_recent_traces(self, test_db):
        """Test querying recent traces."""
        # Add multiple traces
        for i in range(10):
            trace = TraceRecord(
                trace_id=f"trace-{i}",
                task_description=f"Task {i}",
                trace_json={"steps": []},
                combined_score=0.5,
                is_anomalous=False
            )
            test_db.add(trace)
        test_db.commit()
        
        # Query recent 5 traces
        recent = test_db.query(TraceRecord).order_by(
            TraceRecord.created_at.desc()
        ).limit(5).all()
        
        assert len(recent) == 5


class TestFeedbackRecord:
    """Test FeedbackRecord model."""
    
    def test_create_feedback_record(self, test_db):
        """Test creating a feedback record."""
        feedback = FeedbackRecord(
            trace_id="test-123",
            action="continue",
            reward=1.0,
            outcome="success",
            context_summary=[0.1, 0.2, 0.3, 0.4, 1.0]
        )
        
        test_db.add(feedback)
        test_db.commit()
        test_db.refresh(feedback)
        
        assert feedback.id is not None
        assert feedback.trace_id == "test-123"
        assert feedback.reward == 1.0
        assert feedback.created_at is not None
    
    def test_query_feedback_by_trace(self, test_db):
        """Test querying feedback for a specific trace."""
        # Add feedback for multiple traces
        feedback1 = FeedbackRecord(
            trace_id="trace-1",
            action="continue",
            reward=1.0,
            outcome="success"
        )
        feedback2 = FeedbackRecord(
            trace_id="trace-1",
            action="retry_step",
            reward=0.5,
            outcome="success"
        )
        feedback3 = FeedbackRecord(
            trace_id="trace-2",
            action="interrupt_human",
            reward=-0.5,
            outcome="failure"
        )
        
        test_db.add_all([feedback1, feedback2, feedback3])
        test_db.commit()
        
        # Query feedback for trace-1
        feedback_for_trace1 = test_db.query(FeedbackRecord).filter(
            FeedbackRecord.trace_id == "trace-1"
        ).all()
        
        assert len(feedback_for_trace1) == 2


class TestDatabaseOperations:
    """Test database operations."""
    
    def test_bulk_insert_traces(self, test_db):
        """Test bulk inserting traces."""
        traces = [
            TraceRecord(
                trace_id=f"bulk-{i}",
                task_description=f"Bulk task {i}",
                trace_json={"steps": []},
                combined_score=0.5,
                is_anomalous=False
            )
            for i in range(100)
        ]
        
        test_db.bulk_save_objects(traces)
        test_db.commit()
        
        count = test_db.query(TraceRecord).count()
        assert count == 100
    
    def test_aggregate_stats(self, test_db):
        """Test aggregating statistics."""
        from sqlalchemy import func as sql_func
        
        # Add traces with different anomaly status
        for i in range(20):
            trace = TraceRecord(
                trace_id=f"trace-{i}",
                task_description=f"Task {i}",
                trace_json={"steps": []},
                combined_score=0.7 if i < 5 else 0.3,
                is_anomalous=True if i < 5 else False
            )
            test_db.add(trace)
        test_db.commit()
        
        # Get stats
        total = test_db.query(sql_func.count(TraceRecord.id)).scalar()
        anomalous = test_db.query(sql_func.count(TraceRecord.id)).filter(
            TraceRecord.is_anomalous == True
        ).scalar()
        avg_score = test_db.query(sql_func.avg(TraceRecord.combined_score)).scalar()
        
        assert total == 20
        assert anomalous == 5
        assert avg_score is not None
        assert 0 <= avg_score <= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
