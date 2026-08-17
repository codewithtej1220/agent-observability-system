# 🚀 How to Run the Complete System

## One-Click Startup (Recommended)

### Windows:
**Double-click:** `START_SYSTEM.bat`

### All Platforms:
```bash
python run_complete_system.py
```

---

## What Happens When You Run It:

```
1. ✅ Checks if ML models are trained (trains them if not)
2. ✅ Starts API server on http://localhost:8000
3. ✅ Loads demo data (normal + anomalous traces)
4. ✅ Opens dashboard in your browser automatically
5. ✅ Shows real-time statistics
```

---

## Expected Output:

```
╔════════════════════════════════════════════════════════╗
║          AGENT OBSERVABILITY SYSTEM                    ║
║          Complete System Startup                       ║
╚════════════════════════════════════════════════════════╝

STEP 1: Checking ML Models
✅ Models found

STEP 2: Starting API Server
✅ Server started successfully!

STEP 3: Loading Initial Test Data
✅ Normal trace ingested
✅ Anomalous trace ingested

STEP 4: Opening Dashboard
✅ Dashboard opened in browser!

STEP 5: System Status
📊 Current Statistics:
   Total Traces: 22
   Anomalous Traces: 22
   Average Anomaly Score: 0.836

🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉
  ✅ SYSTEM FULLY OPERATIONAL!
  All modules running simultaneously:
     • Unsupervised Learning ✅
     • Reinforcement Learning ✅
     • Supervised Learning ✅
     • API Server ✅
     • Database ✅
     • Monitoring ✅
     • Frontend Dashboard ✅
🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉
```

---

## What You'll See:

### 1. Dashboard Opens Automatically
- URL: `file:///path/to/dashboard.html`
- Shows real-time statistics
- Auto-refreshes every 5 seconds
- Interactive test buttons

### 2. API Server Running
- Base: http://localhost:8000
- Docs: http://localhost:8000/docs
- Stats: http://localhost:8000/stats
- Metrics: http://localhost:8000/metrics

### 3. All Modules Active
- **Unsupervised Learning:** Detecting anomalies
- **Reinforcement Learning:** Recommending actions
- **Supervised Learning:** Learning from feedback
- **Database:** Storing traces
- **Monitoring:** Tracking metrics

---

## Dashboard Features:

The dashboard shows:
- ✅ **API Status** - Green if connected
- 📊 **Statistics** - Total traces, anomalies, avg score
- 🧪 **Test Buttons** - Run tests with one click
- 📋 **Recent Traces** - Last 5 traces with status
- 🔗 **Quick Links** - To API docs, stats, health

---

## Testing the System:

### In Dashboard:
Click the test buttons:
1. **Normal Trace** - See healthy agent behavior
2. **Infinite Loop** - See loop detection
3. **Tool Thrashing** - See tool switching detection
4. **Run All Tests** - Execute complete test suite

### Via API (Postman/curl):
```bash
# Health check
curl http://localhost:8000/health

# Submit trace
curl -X POST http://localhost:8000/ingest_trace \
  -H "Content-Type: application/json" \
  -d @test_healthy.json

# Get stats
curl http://localhost:8000/stats
```

---

## Stopping the System:

Press `Ctrl+C` in the terminal where the system is running.

---

## Troubleshooting:

### Issue: Port 8000 already in use
**Solution:** Kill existing process or use different port:
```bash
python run_complete_system.py --port 8001
```

### Issue: Dashboard doesn't open
**Solution:** Manually open:
- Navigate to project folder
- Double-click `dashboard.html`

### Issue: Models not found
**Solution:** The script automatically trains them, but you can do it manually:
```bash
python scripts/train_pipeline.py
```

### Issue: API server won't start
**Solution:** Check if something is using port 8000:
```bash
# Windows
netstat -ano | findstr :8000

# Kill the process
taskkill /PID <PID> /F
```

---

## Manual Step-by-Step (If Needed):

If you prefer manual control:

```bash
# 1. Activate environment
.\venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac

# 2. Train models (if needed)
python scripts/train_pipeline.py

# 3. Start server
uvicorn api.main:app --reload

# 4. Open dashboard
# Double-click dashboard.html or:
start dashboard.html  # Windows
open dashboard.html   # Mac
xdg-open dashboard.html  # Linux

# 5. Run tests
python test_complete_system.py
```

---

## Production Deployment:

For production, use Docker:

```bash
# Start full stack
docker-compose up -d

# Access
# Dashboard: http://localhost:80
# API: http://localhost:8000
# Grafana: http://localhost:3000
# Prometheus: http://localhost:9090
```

---

## 🎉 Success Indicators:

You know the system is working when:
- ✅ Dashboard shows "API Server Online" (green)
- ✅ Statistics are displayed (Total Traces, Anomalies)
- ✅ Test buttons work and show results
- ✅ Recent traces appear in the list
- ✅ API docs accessible at /docs
- ✅ Metrics endpoint returns data

---

## 📞 Need Help?

1. Check `INDEX.md` for documentation overview
2. Check `PRODUCTION_CHECKLIST.md` for deployment guide
3. Run `python test_complete_system.py` to verify all modules

---

**That's it! Your system should be fully operational! 🚀**
