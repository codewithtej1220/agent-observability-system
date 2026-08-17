# Changelog

All notable changes to the Agent Observability System.

## [1.0.0] - 2026-08-17

### Major Release: Production-Ready System

#### Added
- **Real Data Training**: 1,200+ traces from HuggingFace datasets
- **PostgreSQL Database**: Migrated from SQLite to PostgreSQL with SQLAlchemy ORM
- **Authentication**: API key-based authentication with RBAC framework
- **Rate Limiting**: Token bucket algorithm (100 req/min)
- **RL Policy Persistence**: Auto-saves every 10 feedback updates
- **React Dashboard**: Real-time metrics visualization with Recharts
- **Docker Support**: docker-compose.yml and Dockerfile
- **Kubernetes**: k8s-deployment.yml manifests
- **CI/CD**: GitHub Actions workflow
- **Environment Config**: .env-based configuration with dotenv

#### Changed
- **Database**: SQLite → PostgreSQL (Supabase)
- **Storage Layer**: Direct SQL → SQLAlchemy ORM
- **API Endpoints**: All endpoints now use database sessions
- **Frontend**: Added API key authentication
- **Documentation**: Consolidated into professional README

#### Fixed
- JSON parsing errors in React dashboard
- Rate limiting not being enforced
- RL policy not persisting across restarts
- Frontend fetch errors with proper error handling
- Authentication bypass vulnerabilities

#### Security
- Environment variables for all secrets
- API keys enforced on protected endpoints
- SQL injection prevention via ORM
- CORS configuration
- Input validation with Pydantic

### Training Data
- **facebook/xlsum**: Summarization traces
- **lmsys/chatbot_arena_conversations**: Production chatbot data
- **HuggingFaceH4/ultrachat_200k**: High-quality dialogues
- **HuggingFaceH4/no_robots**: Human-written conversations
- **lmsys/toxic-chat**: Failure mode examples

### Evaluation
- Proper train/validation/test splits (64/16/20)
- Stratified sampling
- Held-out test set evaluation
- Recall: 75-85% | Precision: 70-80% | F1: 72-82%

---

## [0.2.0] - 2026-08-10 (Week 2)

### PostgreSQL Migration

#### Added
- SQLAlchemy ORM models
- Supabase PostgreSQL connection
- Database session management
- Connection pooling (10 base + 20 overflow)
- Alembic migration support

#### Changed
- Replaced storage.py with database.py
- Updated all API endpoints for PostgreSQL
- Environment-based database URL

#### Removed
- SQLite storage implementation
- Direct SQL queries

---

## [0.1.0] - 2026-08-03 (Week 1)

### Initial Release with Critical Fixes

#### Added
- Real data loader for HuggingFace datasets
- Proper train/validation/test splits
- API key authentication framework
- Rate limiting implementation
- RL policy save/load functionality
- Frontend API key configuration

#### Changed
- Training pipeline uses real data (not synthetic)
- Proper evaluation metrics on test set
- API requires authentication

#### Fixed
- Training on synthetic data only
- No train/test splits
- Authentication not enforced
- Rate limiting inactive
- RL policy lost on restart

---

## [0.0.1] - 2026-07-27 (Initial Prototype)

### Prototype Release

#### Added
- Three learning paradigms (unsupervised, RL, supervised)
- IsolationForest anomaly detection
- HDBSCAN clustering
- LinUCB contextual bandit
- FastAPI backend
- Basic frontend dashboard
- Synthetic data generation

#### Known Issues
- Training on synthetic data only
- No train/test splits
- No authentication
- SQLite database (not production-ready)
- No rate limiting
- RL policy not persistent

---

## Version History Summary

| Version | Date | Key Feature | Status |
|---------|------|-------------|--------|
| 1.0.0 | 2026-08-17 | Production-ready with PostgreSQL | Current |
| 0.2.0 | 2026-08-10 | PostgreSQL migration | Stable |
| 0.1.0 | 2026-08-03 | Real data + authentication | Stable |
| 0.0.1 | 2026-07-27 | Initial prototype | Deprecated |

---

## Upgrade Guide

### From 0.2.0 to 1.0.0
No breaking changes. Environment variables remain the same.

### From 0.1.0 to 0.2.0
**Breaking Change:** Database migration required
1. Export data from SQLite
2. Update DATABASE_URL in .env
3. Run: `python api/database.py` to create tables
4. Import data to PostgreSQL (if needed)

### From 0.0.1 to 0.1.0
**Breaking Change:** Authentication now required
1. Add API keys to requests
2. Update client code with X-API-Key header
3. Retrain models with real data

---

## Roadmap

### Version 1.1.0 (Planned)
- [ ] Sentry error monitoring integration
- [ ] UptimeRobot health monitoring
- [ ] README badges
- [ ] Comprehensive test suite
- [ ] Load testing results

### Version 1.2.0 (Future)
- [ ] Grafana dashboards
- [ ] Prometheus metrics
- [ ] Advanced RBAC
- [ ] Multi-tenancy support
- [ ] Deep learning integration

### Version 2.0.0 (Future)
- [ ] Real-time streaming analysis
- [ ] Distributed tracing
- [ ] Advanced anomaly detection models
- [ ] Auto-remediation capabilities
