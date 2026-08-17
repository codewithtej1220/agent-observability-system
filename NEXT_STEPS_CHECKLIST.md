# ✅ Next Steps Checklist

## Immediate Actions (Right Now)

- [ ] **Test the fixes**
  ```bash
  # 1. Install datasets library
  pip install datasets
  
  # 2. Train with real data
  python scripts/train_pipeline.py
  
  # 3. Start API
  uvicorn api.main:app --reload --port 8001
  
  # 4. Test auth (should fail)
  curl -X POST http://localhost:8001/ingest_trace -d '{}'
  
  # 5. Test auth (should work)
  curl -X POST http://localhost:8001/ingest_trace -H "X-API-Key: dev-key-12345" -H "Content-Type: application/json" -d '{"task_description":"test","steps":[]}'
  ```

- [ ] **Verify React dashboard works**
  ```bash
  cd frontend
  npm start
  # Open http://localhost:3000
  ```

- [ ] **Check artifacts created**
  ```bash
  ls artifacts/
  # Should see: embedder.pkl, detector.pkl
  # After feedback: bandit_state.npz
  ```

---

## Week 2: Database Decision (Choose ONE)

### Option A: Migrate to PostgreSQL ⭐ Recommended
- [ ] Sign up for [Neon](https://neon.tech) (free tier, no credit card)
- [ ] Get database connection string
- [ ] Set `DATABASE_URL` environment variable
- [ ] Update `api/main.py` to use `database.py` instead of `storage.py`
- [ ] Test migrations
- [ ] Delete `storage.py` once confirmed working

### Option B: Own SQLite Limitation
- [ ] Delete `api/database.py` (unused code)
- [ ] Update README with SQLite limitation clearly stated
- [ ] Document "single-instance deployment only"
- [ ] Accept no horizontal scaling

**Decision deadline**: End of Week 2

---

## Week 3: Monitoring & CI/CD

### Git & CI/CD
- [ ] Create public GitHub repository
- [ ] Push all code to GitHub
  ```bash
  git init
  git add .
  git commit -m "Week 1 fixes: real data, auth, rate limiting, RL persistence"
  git remote add origin <your-repo-url>
  git push -u origin main
  ```
- [ ] Verify GitHub Actions CI runs automatically
- [ ] Add status badge to README

### Monitoring Setup
- [ ] Sign up for [Sentry](https://sentry.io) (free tier, 5k errors/month)
- [ ] Get Sentry DSN
- [ ] Set `SENTRY_DSN` environment variable
- [ ] Test error tracking works
- [ ] Sign up for [UptimeRobot](https://uptimerobot.com) (free, 50 monitors)
- [ ] Add `/health` endpoint monitoring
- [ ] Configure email/Slack alerts

### Optional: Metrics
- [ ] Sign up for [Grafana Cloud](https://grafana.com/products/cloud) (free tier)
- [ ] Configure Prometheus integration
- [ ] Create basic dashboard
- [ ] Set up alerts for anomaly rate, errors

---

## Week 4: Testing & Cleanup

### Testing
- [ ] Write behavioral tests (not just status codes)
  ```python
  def test_anomalous_scores_higher_than_healthy():
      healthy = ingest_trace(healthy_trace)
      anomalous = ingest_trace(looping_trace)
      assert anomalous["combined_score"] > healthy["combined_score"]
  ```
- [ ] Test rate limiting actually triggers 429
- [ ] Test auth actually blocks unauthorized requests
- [ ] Test RL persistence survives restart
- [ ] Run load tests with Locust

### Cleanup Dead Code
- [ ] **Decision**: Deep learning - wire in OR delete
  - If wire in: integrate `train_deep_learning.py` with main pipeline
  - If delete: remove `train_deep_learning.py`, `requirements_dl.txt`
- [ ] Remove unused imports
- [ ] Delete commented-out code
- [ ] Clean up duplicate documentation

### Configuration
- [ ] Add `.env` file support
  ```bash
  pip install python-dotenv
  ```
- [ ] Move hardcoded config to environment variables
- [ ] Create `.env.example` (commit this)
- [ ] Add `.env` to `.gitignore`

### Documentation
- [ ] Create architecture diagram (use Excalidraw or Mermaid)
- [ ] Add to README
- [ ] Update API documentation
- [ ] Add troubleshooting section

---

## Optional: Kubernetes Testing

**Only if you want K8s experience (not needed for deployment)**

- [ ] Install [kind](https://kind.sigs.k8s.io/) or [minikube](https://minikube.sigs.k8s.io/)
- [ ] Test manifest locally
  ```bash
  kind create cluster
  kubectl apply -f k8s-deployment.yml
  kubectl get pods -w
  ```
- [ ] Fix any issues found
- [ ] Update manifest with actual database choice
- [ ] Add PersistentVolumeClaim if keeping SQLite

**OR**
- [ ] Delete `k8s-deployment.yml` if not using Kubernetes
- [ ] Deploy to simpler platform (Railway, Render, Fly.io)

---

## Deployment Checklist

### Prerequisites
- [ ] Database choice made (PostgreSQL or SQLite documented)
- [ ] Monitoring configured (Sentry DSN set)
- [ ] CI/CD running (tests passing)
- [ ] Environment variables documented

### Deploy Options

#### Option A: Railway.app (Easiest)
- [ ] Sign up for [Railway](https://railway.app)
- [ ] Connect GitHub repository
- [ ] Add environment variables
- [ ] Deploy
- [ ] Test deployed URL

#### Option B: Render.com
- [ ] Sign up for [Render](https://render.com)
- [ ] Create new Web Service
- [ ] Connect GitHub repository
- [ ] Configure build/start commands
- [ ] Add environment variables
- [ ] Deploy

#### Option C: Fly.io
- [ ] Install flyctl
- [ ] `fly launch`
- [ ] Configure `fly.toml`
- [ ] `fly deploy`

### Post-Deployment
- [ ] Test all endpoints on deployed URL
- [ ] Verify auth works
- [ ] Verify rate limiting works
- [ ] Check monitoring (Sentry, UptimeRobot)
- [ ] Update README with live URL
- [ ] Add deployed URL to portfolio

---

## Portfolio Presentation

### README Updates
- [ ] Add "Live Demo" link
- [ ] Add CI status badge
- [ ] Add screenshots of dashboard
- [ ] Add metrics/stats from usage
- [ ] Highlight key technical decisions

### Portfolio Site
- [ ] Add project card with screenshot
- [ ] Write project description
- [ ] Link to GitHub repo
- [ ] Link to live demo
- [ ] List technologies used

### LinkedIn/Resume
- [ ] Add project to experience/projects
- [ ] Highlight: "Trained on 1,200+ real agent traces"
- [ ] Highlight: "Proper ML evaluation with test set"
- [ ] Highlight: "Secure API with auth + rate limiting"
- [ ] Highlight: "Persistent reinforcement learning"

---

## Success Metrics

### Code Quality
- [ ] All tests passing
- [ ] No unused code
- [ ] All features documented
- [ ] .env for configuration
- [ ] CI/CD green

### Functionality
- [ ] Can ingest traces
- [ ] Can detect anomalies
- [ ] Can recommend actions
- [ ] Can learn from feedback
- [ ] Learning persists

### Security
- [ ] Auth enforced
- [ ] Rate limiting active
- [ ] Input validated
- [ ] Secrets in .env
- [ ] HTTPS in production

### Operations
- [ ] Monitoring active
- [ ] Alerts configured
- [ ] Logs aggregated
- [ ] Database backed up
- [ ] Deploy automated

### Documentation
- [ ] Setup guide clear
- [ ] API documented
- [ ] Architecture explained
- [ ] Limitations stated
- [ ] Examples provided

---

## Priority Order

### Do First (Critical):
1. ✅ Test Week 1 fixes work
2. ⏰ Week 2: Database decision
3. ⏰ Week 3: Push to GitHub + CI/CD

### Do Second (Important):
4. ⏰ Week 3: Monitoring (Sentry + UptimeRobot)
5. ⏰ Week 4: Real tests (behavioral)
6. ⏰ Week 4: Cleanup dead code

### Do Third (Nice to Have):
7. Configuration management (.env)
8. Architecture diagram
9. Deploy to cloud platform
10. Portfolio updates

### Optional (Only if Relevant):
11. Kubernetes testing
12. Deep learning integration
13. Grafana dashboards
14. Load testing at scale

---

## Timeline

### This Week
- ✅ **Day 1-2**: Week 1 fixes (DONE!)
- ⏰ **Day 3-4**: Test everything works
- ⏰ **Day 5**: Make database decision

### Next 3 Weeks
- **Week 2**: Database migration or cleanup
- **Week 3**: CI/CD + monitoring
- **Week 4**: Testing + cleanup + deploy

### After 4 Weeks
- **Deployed MVP** on cloud platform
- **Monitoring active** with alerts
- **CI/CD running** automatically
- **Portfolio ready** to show

---

## Quick Reference

```bash
# Train models
python scripts/train_pipeline.py

# Start API
uvicorn api.main:app --reload --port 8001

# Start frontend
cd frontend && npm start

# Test auth
curl -H "X-API-Key: dev-key-12345" http://localhost:8001/stats

# Run tests
python test_complete_system.py

# Deploy (after choosing platform)
git push origin main  # Triggers CI/CD
```

---

## Questions to Answer

- [ ] **Database**: PostgreSQL or SQLite?
- [ ] **Deep Learning**: Wire in or delete?
- [ ] **Kubernetes**: Test or remove?
- [ ] **Deployment**: Which platform?

---

## Resources

- [Neon PostgreSQL](https://neon.tech) - Free tier, serverless
- [Sentry](https://sentry.io) - Error tracking
- [UptimeRobot](https://uptimerobot.com) - Uptime monitoring
- [Railway](https://railway.app) - Easy deployment
- [Render](https://render.com) - Alternative deployment
- [Fly.io](https://fly.io) - Another option

---

## Final Goal

**By end of 4 weeks:**
- ✅ Trained on real data
- ✅ Honest evaluation metrics
- ✅ Secure and protected API
- ✅ Persistent learning
- ✅ Monitoring active
- ✅ CI/CD running
- ✅ Deployed and live
- ✅ Portfolio-ready

**Current progress: Week 1 complete (25%)**

---

**Next immediate action**: Run the verification tests in this document!
