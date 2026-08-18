# Testing Guide

## Overview

Comprehensive testing suite for the Agent Observability System with unit tests, integration tests, API tests, and load tests.

---

## Test Structure

```
tests/
├── conftest.py           # Shared fixtures and configuration
├── test_api.py          # API endpoint tests (integration)
├── test_models.py       # ML model tests (unit)
├── test_database.py     # Database operation tests (unit)
├── load_test.py         # Load testing with Locust
└── test_data/           # Test data files (if needed)
```

---

## Setup

### 1. Install Test Dependencies

```bash
# Activate virtual environment
.\venv\Scripts\activate

# Install test dependencies
pip install -r requirements.txt
```

**Test dependencies included:**
- `pytest` - Testing framework
- `pytest-cov` - Code coverage
- `pytest-asyncio` - Async test support
- `pytest-timeout` - Test timeouts
- `httpx` - HTTP client for FastAPI tests
- `locust` - Load testing

### 2. Verify Installation

```bash
pytest --version
# Should show: pytest 8.3.3
```

---

## Running Tests

### Run All Tests

```bash
# Run all tests with coverage
pytest

# Run with verbose output
pytest -v

# Run with coverage report
pytest --cov --cov-report=html
```

### Run Specific Test Files

```bash
# API tests only
pytest tests/test_api.py

# Model tests only
pytest tests/test_models.py

# Database tests only
pytest tests/test_database.py
```

### Run Specific Test Classes

```bash
# Test health endpoints only
pytest tests/test_api.py::TestHealthEndpoints

# Test anomaly detector only
pytest tests/test_models.py::TestAnomalyDetector
```

### Run Specific Test Functions

```bash
# Test single function
pytest tests/test_api.py::TestHealthEndpoints::test_health_check
```

### Run Tests by Marker

```bash
# Run only unit tests (fast)
pytest -m unit

# Run only integration tests
pytest -m integration

# Run only API tests
pytest -m api

# Exclude slow tests
pytest -m "not slow"
```

---

## Test Coverage

### Generate Coverage Report

```bash
# Run tests with coverage
pytest --cov

# Generate HTML report
pytest --cov --cov-report=html

# Open HTML report
# Windows:
start htmlcov/index.html

# macOS/Linux:
open htmlcov/index.html
```

### Coverage Targets

**Current Target:** 60% minimum (configured in pytest.ini)

**By Component:**
- `api/` - API endpoints: **Target 70%+**
- `anomaly_model/` - ML models: **Target 80%+**
- `embedding_pipeline/` - Feature extraction: **Target 75%+**
- `rl_policy/` - RL bandit: **Target 80%+**

**Why these targets?**
- High coverage for critical business logic
- ML models are deterministic and testable
- API endpoints should be thoroughly tested
- Some code paths (error handling) harder to test

---

## Test Categories

### 1. Unit Tests (Fast, Isolated)

**Purpose:** Test individual functions/classes in isolation

**Examples:**
- ML model training and scoring
- Feature extraction
- RL policy updates
- Database model creation

**Characteristics:**
- ✅ Fast (< 1 second each)
- ✅ No external dependencies
- ✅ Use mocks/stubs
- ✅ Can run in parallel

**Run:**
```bash
pytest -m unit
```

### 2. Integration Tests (Slower, Connected)

**Purpose:** Test components working together

**Examples:**
- API endpoint + database
- API endpoint + ML models
- End-to-end trace ingestion flow

**Characteristics:**
- ⏱️ Slower (1-5 seconds each)
- 🔌 May use test database
- 🔄 Test real interactions
- ✅ More realistic

**Run:**
```bash
pytest -m integration
```

### 3. API Tests

**Purpose:** Test all HTTP endpoints

**Coverage:**
- ✅ Health endpoints (`/health`, `/stats`)
- ✅ Trace ingestion (`/ingest_trace`)
- ✅ Feedback (`/feedback`)
- ✅ Trace retrieval (`/traces`)
- ✅ Authentication (API keys)
- ✅ Rate limiting
- ✅ Error handling (4xx, 5xx)

**Run:**
```bash
pytest tests/test_api.py -v
```

### 4. Load Tests

**Purpose:** Test system under load

**Tool:** Locust (web-based load testing)

**Scenarios:**
- Light load: 10-50 users
- Medium load: 50-200 users
- Heavy load: 200+ users

**Run:**
```bash
# Start Locust web UI
locust -f tests/load_test.py --host http://localhost:8001

# Open browser: http://localhost:8089
# Configure: Number of users, spawn rate
# Start load test
```

---

## Test Configuration

### pytest.ini

**Key settings:**
```ini
[pytest]
testpaths = tests              # Where to find tests
addopts = -v --cov             # Default options
markers = unit, integration    # Test markers
minversion = 3.8               # Minimum Python version
timeout = 300                  # Test timeout (5 min)
```

### conftest.py

**Shared fixtures:**
- `test_data_dir` - Test data directory
- `sample_trace_json` - Valid trace example
- `anomalous_trace_json` - Anomalous trace example
- `valid_api_key` - API key for testing
- `invalid_api_key` - Invalid API key

**Usage:**
```python
def test_something(sample_trace_json, valid_api_key):
    # Use fixtures in your tests
    pass
```

---

## Writing Tests

### Test Structure

```python
import pytest

class TestFeatureName:
    """Test a specific feature."""
    
    def test_happy_path(self):
        """Test the normal, expected behavior."""
        # Arrange
        input_data = ...
        
        # Act
        result = function_to_test(input_data)
        
        # Assert
        assert result == expected_value
    
    def test_edge_case(self):
        """Test edge cases."""
        # Test empty input, None, etc.
        pass
    
    def test_error_handling(self):
        """Test error conditions."""
        with pytest.raises(ValueError):
            function_to_test(invalid_input)
```

### Best Practices

**1. Arrange-Act-Assert (AAA)**
```python
def test_trace_embedding():
    # Arrange: Set up test data
    trace = create_test_trace()
    embedder = TraceEmbedder()
    
    # Act: Execute the function
    embedding = embedder.transform([trace])
    
    # Assert: Verify the result
    assert embedding.shape[0] == 1
    assert embedding.shape[1] > 0
```

**2. Use Descriptive Names**
```python
# Good
def test_ingest_trace_with_empty_steps_returns_success():
    pass

# Bad
def test_1():
    pass
```

**3. Test One Thing Per Test**
```python
# Good
def test_health_endpoint_returns_200():
    response = client.get("/health")
    assert response.status_code == 200

def test_health_endpoint_returns_correct_json():
    response = client.get("/health")
    assert response.json() == {"status": "ok"}

# Bad (testing too many things)
def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["content-type"] == "application/json"
```

**4. Use Fixtures for Setup**
```python
@pytest.fixture
def trained_model():
    """Provide a trained model for tests."""
    embeddings = np.random.randn(100, 50)
    detector = AnomalyDetector()
    detector.fit(embeddings)
    return detector

def test_scoring(trained_model):
    # trained_model is automatically provided
    scores = trained_model.score(test_data)
    assert len(scores) > 0
```

**5. Mock External Dependencies**
```python
from unittest.mock import patch, MagicMock

@patch('api.main._embedder')
def test_ingest_with_mock(mock_embedder):
    # Mock the embedder to avoid loading real model
    mock_embedder.transform.return_value = np.array([[0.1, 0.2, 0.3]])
    
    response = client.post("/ingest_trace", json=trace_data)
    assert response.status_code == 200
```

---

## Common Test Scenarios

### Testing API Endpoints

```python
from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)

def test_endpoint():
    # GET request
    response = client.get("/health")
    assert response.status_code == 200
    
    # POST with JSON
    data = {"key": "value"}
    response = client.post("/endpoint", json=data)
    
    # With headers
    headers = {"X-API-Key": "test-key"}
    response = client.get("/protected", headers=headers)
```

### Testing ML Models

```python
import numpy as np
from anomaly_model.model import AnomalyDetector

def test_model_training():
    # Create synthetic data
    X_train = np.random.randn(100, 10)
    
    # Train model
    model = AnomalyDetector()
    model.fit(X_train)
    
    # Test prediction
    X_test = np.random.randn(10, 10)
    scores = model.score(X_test)
    
    # Verify output format
    assert len(scores) == 10
    assert all(0 <= s.combined_score <= 1 for s in scores)
```

### Testing Database Operations

```python
from api.database import TraceRecord

def test_database_insert(test_db):
    # Create record
    trace = TraceRecord(
        trace_id="test-123",
        task_description="Test",
        trace_json={},
        combined_score=0.5,
        is_anomalous=False
    )
    
    # Insert
    test_db.add(trace)
    test_db.commit()
    
    # Verify
    result = test_db.query(TraceRecord).filter_by(trace_id="test-123").first()
    assert result is not None
    assert result.task_description == "Test"
```

### Testing Async Functions

```python
import pytest

@pytest.mark.asyncio
async def test_async_function():
    result = await async_function()
    assert result == expected_value
```

---

## Continuous Integration

### GitHub Actions Integration

The `.github/workflows/ci-cd.yml` file runs tests automatically on every push:

```yaml
- name: Run tests
  run: |
    pytest --cov --cov-report=xml
    
- name: Upload coverage
  uses: codecov/codecov-action@v3
  with:
    files: ./coverage.xml
```

### Pre-commit Testing

**Set up pre-commit hook:**

```bash
# Create .git/hooks/pre-commit
cat > .git/hooks/pre-commit << 'EOF'
#!/bin/sh
echo "Running tests before commit..."
pytest -x
if [ $? -ne 0 ]; then
    echo "Tests failed! Commit aborted."
    exit 1
fi
EOF

# Make executable
chmod +x .git/hooks/pre-commit
```

---

## Load Testing

### Run Load Tests with Locust

**1. Start your API:**
```bash
uvicorn api.main:app --port 8001
```

**2. Start Locust:**
```bash
locust -f tests/load_test.py --host http://localhost:8001
```

**3. Open Web UI:**
- Browser: http://localhost:8089
- Set number of users: 50
- Set spawn rate: 10 users/second
- Click "Start Swarming"

**4. Monitor Results:**
- Requests per second
- Response times (p50, p95, p99)
- Failure rate
- Charts and graphs

### Load Test Scenarios

**Light Load (10-50 users):**
```bash
locust -f tests/load_test.py --host http://localhost:8001 \
  --users 50 --spawn-rate 10 --run-time 5m --headless
```

**Medium Load (50-200 users):**
```bash
locust -f tests/load_test.py --host http://localhost:8001 \
  --users 200 --spawn-rate 20 --run-time 10m --headless
```

**Heavy Load (200+ users):**
```bash
locust -f tests/load_test.py --host http://localhost:8001 \
  --users 500 --spawn-rate 50 --run-time 15m --headless
```

### Load Test Metrics

**Key Metrics to Watch:**
- **Request Rate:** Requests/second the system can handle
- **Response Time:** p95 and p99 latency (should be < 100ms)
- **Failure Rate:** Should be < 1%
- **Throughput:** Successful requests/second

**Performance Targets:**
- Normal load: 100 req/sec with <100ms p95
- Peak load: 50 req/sec with <200ms p95
- No errors under normal load

---

## Troubleshooting Tests

### Tests Failing?

**1. Check Environment Variables**
```bash
# Make sure test environment is set
pytest --collect-only  # See what tests are collected
```

**2. Check Database Connection**
```bash
# Tests use in-memory SQLite by default
# If tests fail with DB errors, check conftest.py
```

**3. Check Model Artifacts**
```bash
# Some tests need trained models
python scripts/train_pipeline.py
```

**4. Run Tests in Isolation**
```bash
# Run one test at a time
pytest tests/test_api.py::test_health_check -v
```

### Coverage Too Low?

**1. Identify Uncovered Code:**
```bash
pytest --cov --cov-report=term-missing
# Shows line numbers not covered
```

**2. Add Tests for Uncovered Lines:**
- Focus on critical business logic first
- Error handling can be lower priority
- Some lines may be hard to cover (defensive code)

**3. Adjust Coverage Threshold:**
```ini
# In pytest.ini
--cov-fail-under=60  # Adjust this number
```

---

## Test Checklist

Before pushing code, ensure:

- [ ] All tests pass locally (`pytest`)
- [ ] Code coverage meets threshold (60%+)
- [ ] New features have tests
- [ ] Bug fixes have regression tests
- [ ] No skipped tests without good reason
- [ ] Load tests pass (if performance-critical changes)

---

## Resources

- **pytest documentation:** https://docs.pytest.org/
- **pytest-cov documentation:** https://pytest-cov.readthedocs.io/
- **Locust documentation:** https://docs.locust.io/
- **FastAPI testing:** https://fastapi.tiangolo.com/tutorial/testing/

---

## Next Steps

1. **Run tests:** `pytest -v`
2. **Check coverage:** `pytest --cov --cov-report=html`
3. **Fix failing tests** (if any)
4. **Add more tests** for uncovered code
5. **Run load tests:** `locust -f tests/load_test.py`
6. **Integrate with CI/CD** (already configured)

---

**Goal:** Achieve 70%+ code coverage with comprehensive, maintainable tests that give confidence in the system's correctness.
