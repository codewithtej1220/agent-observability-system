# Setup Guide

## Prerequisites

- Python 3.8+
- Node.js 14+ (for frontend)
- PostgreSQL database (Supabase recommended)
- Git

## Installation

### 1. Clone Repository
```bash
git clone https://github.com/codewithtej1220/agent-observability-system.git
cd agent-observability-system
```

### 2. Set Up Python Environment
```bash
# Create virtual environment
python -m venv venv

# Activate (Windows)
.\venv\Scripts\activate

# Activate (macOS/Linux)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure Environment
```bash
# Copy example configuration
cp .env.example .env

# Edit .env file with your settings
# Required: DATABASE_URL, SECRET_KEY
```

**Example .env:**
```bash
DATABASE_URL=postgresql://user:pass@host:5432/dbname
SECRET_KEY=your-secret-key-change-this
ENVIRONMENT=development
ARTIFACTS_DIR=artifacts
```

### 4. Initialize Database
```bash
# Create tables
python api/database.py
```

### 5. Train Models
```bash
# Train on real data and generate model artifacts
python scripts/train_pipeline.py
```

This creates:
- `artifacts/embedder.pkl` - Feature extraction model
- `artifacts/detector.pkl` - Anomaly detection model
- `artifacts/bandit_state.npz` - RL policy (auto-created on first feedback)

### 6. Start Backend API
```bash
# Development mode with auto-reload
uvicorn api.main:app --reload --port 8001
```

API will be available at: http://localhost:8001

### 7. Start Frontend Dashboard
```bash
# Open new terminal
cd frontend

# Install dependencies (first time only)
npm install

# Start development server
npm start
```

Dashboard will be available at: http://localhost:3000

## Verification

### Test API Health
```bash
curl http://localhost:8001/health
```

Expected: `{"status": "ok"}`

### Test Authentication
```bash
# Without API key (should fail)
curl -X POST http://localhost:8001/ingest_trace

# With API key (should succeed)
curl -H "X-API-Key: dev-key-12345" \
     -H "Content-Type: application/json" \
     -X POST http://localhost:8001/ingest_trace \
     -d '{"task_description":"test","steps":[]}'
```

### View API Documentation
Open: http://localhost:8001/docs

## Default API Keys

**Development:**
- Key: `dev-key-12345`
- Role: admin
- Rate limit: 1000 req/min

**Production:**
- Key: `prod-key-67890`
- Role: user
- Rate limit: 100 req/min

**Note:** Change these in production! Update `api/auth.py` to use environment variables or database storage.

## Docker Deployment

### Using Docker Compose
```bash
# Build and start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

### Manual Docker Build
```bash
# Build image
docker build -t agent-observability:latest .

# Run container
docker run -p 8001:8001 \
  -e DATABASE_URL=postgresql://... \
  -e SECRET_KEY=... \
  agent-observability:latest
```

## Kubernetes Deployment

```bash
# Apply deployment
kubectl apply -f k8s-deployment.yml

# Check status
kubectl get pods -l app=agent-observability

# View logs
kubectl logs -f deployment/agent-observability-api
```

## Troubleshooting

### Virtual Environment Not Activating
**Windows:** Use `.\venv\Scripts\activate`  
**macOS/Linux:** Use `source venv/bin/activate`

### Database Connection Error
- Verify DATABASE_URL in .env file
- Check PostgreSQL is running and accessible
- Test connection: `psql $DATABASE_URL`

### Missing Model Artifacts
Run training pipeline: `python scripts/train_pipeline.py`

### Port Already in Use
Change port: `uvicorn api.main:app --reload --port 8002`

### Frontend Not Connecting to API
- Check API is running on port 8001
- Update API_BASE_URL in `frontend/src/App.jsx` if needed
- Verify CORS settings in `api/main.py`

### Rate Limit Errors (429)
- Default: 100 requests/minute per endpoint
- Use `dev-key-12345` for higher limit (1000 req/min)
- Adjust limits in `api/rate_limiter.py`

## Development Tips

### Retrain Models
```bash
python scripts/train_pipeline.py
```

### Run Tests
```bash
# All tests
pytest tests/

# Specific test
pytest tests/test_models.py

# With coverage
pytest --cov=api --cov=anomaly_model tests/
```

### View Database Tables
```bash
# Using psql
psql $DATABASE_URL

# List tables
\dt

# View traces
SELECT * FROM traces LIMIT 10;
```

### Clear Database
```python
# In Python shell
from api.database import drop_all, init_db

drop_all()  # Delete all tables
init_db()   # Recreate tables
```

## Production Deployment Checklist

- [ ] Change SECRET_KEY in .env
- [ ] Update API keys (move to database or env vars)
- [ ] Set ENVIRONMENT=production
- [ ] Use production DATABASE_URL
- [ ] Configure Sentry DSN (optional)
- [ ] Set up HTTPS/TLS
- [ ] Configure firewall rules
- [ ] Set up monitoring (UptimeRobot, Grafana)
- [ ] Enable backup strategy for PostgreSQL
- [ ] Test rate limiting
- [ ] Review CORS settings
- [ ] Set up logging aggregation

## Additional Resources

- **README.md** - Project overview and API reference
- **ARCHITECTURE.md** - System design and technical details
- **CHANGELOG.md** - Version history
- **API Docs** - http://localhost:8001/docs (when running)
