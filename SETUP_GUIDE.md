# Project Setup Guide

## ✅ Setup Complete!

Your development environment has been successfully configured. Here's what's been set up:

### 1. Virtual Environment
- Created at: `venv/`
- Python version: 3.10.11
- All dependencies installed from `requirements.txt`

### 2. Model Training
- Training completed successfully
- Artifacts saved to `artifacts/`:
  - `embedder.pkl` - Trace embedding model
  - `detector.pkl` - Anomaly detection model
- Trained on 120 synthetic traces (40 pathological, 80 healthy)
- Achieved 100% recall and 98% precision on training set

### 3. API Server
- Running at: http://localhost:8000
- Status: Active and tested ✓
- Available endpoints:
  - `GET /health` - Health check
  - `POST /ingest_trace` - Submit agent traces for analysis
  - `POST /feedback` - Update RL policy with outcome feedback
  - `GET /traces` - View recent traces
  - `GET /stats` - Get system statistics

### 4. VS Code Configuration
Created `.vscode/` directory with:

#### `settings.json`
- Python interpreter set to `venv\Scripts\python.exe`
- Virtual environment auto-activation enabled
- Analysis paths configured

#### `launch.json`
Three debug configurations:
1. **Python: Uvicorn API Server (Debug)**
   - Runs uvicorn as a module for full debugging
   - Set breakpoints in `api/main.py` or `anomaly_model/model.py`
   - Auto-reload enabled
   - Press F5 to start debugging

2. **Python: Train Pipeline**
   - Debug the training script
   - Set breakpoints in `scripts/train_pipeline.py`

3. **Python: Current File**
   - Debug any Python file currently open

---

## 🚀 Quick Start

### Activate Virtual Environment
```bash
.\venv\Scripts\activate
```

### Start API Server (Manual)
```bash
uvicorn api.main:app --reload
```

### Start API Server (Debug Mode)
1. Open VS Code
2. Go to Run and Debug (Ctrl+Shift+D)
3. Select "Python: Uvicorn API Server (Debug)"
4. Press F5
5. Set breakpoints in your code
6. Test endpoints to hit your breakpoints

---

## 🧪 Testing the API

### Test Health Endpoint
Open browser: http://localhost:8000/health

### Test Trace Ingestion (PowerShell)
```powershell
$body = @'
{
  "task_description": "example task",
  "steps": [
    {
      "step_id": 0,
      "action_type": "tool_call",
      "tool_name": "search",
      "arguments": {"query": "task info"},
      "output": "Found 3 relevant results.",
      "latency_ms": 150,
      "tokens_used": 20
    }
  ]
}
'@

Invoke-WebRequest -Uri "http://localhost:8000/ingest_trace" `
  -Method POST `
  -ContentType "application/json" `
  -Body $body `
  -UseBasicParsing | Select-Object -ExpandProperty Content
```

### View Statistics
Open browser: http://localhost:8000/stats

### Interactive API Documentation
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

---

## 🐛 Debugging Workflow

### Setting Breakpoints
1. Open `api/main.py` or `anomaly_model/model.py`
2. Click in the gutter (left of line numbers) to set breakpoints
3. Start debug configuration "Python: Uvicorn API Server (Debug)"
4. Send a request to the API
5. Execution will pause at your breakpoints
6. Inspect variables, step through code, evaluate expressions

### Common Breakpoint Locations
- `api/main.py:99` - `ingest_trace()` function entry
- `api/main.py:105` - After trace embedding
- `api/main.py:106` - After anomaly scoring
- `anomaly_model/model.py` - Score calculation logic
- `rl_policy/bandit.py` - Action selection

### Debug Console
When paused at a breakpoint:
- View local variables in the Variables pane
- Use Debug Console to evaluate expressions
- Step over (F10), step into (F11), or continue (F5)

---

## 📁 Project Structure

```
project1-agent-observability/
├── venv/                    # Virtual environment
├── .vscode/                 # VS Code configuration
│   ├── settings.json        # Python interpreter settings
│   └── launch.json          # Debug configurations
├── artifacts/               # Trained model artifacts
│   ├── embedder.pkl
│   └── detector.pkl
├── agent_harness/           # Instrumented agent loop
├── anomaly_model/           # Anomaly detection
├── api/                     # FastAPI service
├── data/                    # Synthetic data generation
├── embedding_pipeline/      # Trace embedding
├── rl_policy/               # RL bandit policy
└── scripts/                 # Training scripts
```

---

## 🔧 Troubleshooting

### Reactivate Virtual Environment
If your terminal doesn't show `(venv)`:
```bash
.\venv\Scripts\activate
```

### Retrain Models
If you modify the training pipeline:
```bash
python scripts\train_pipeline.py
```

### Check Python Interpreter in VS Code
1. Press Ctrl+Shift+P
2. Type "Python: Select Interpreter"
3. Choose the one with path containing `venv\Scripts\python.exe`

### Port Already in Use
If port 8000 is busy:
```bash
uvicorn api.main:app --reload --port 8001
```

---

## 🎯 Next Steps

1. **Explore the API**: Open http://localhost:8000/docs for interactive documentation
2. **Debug the code**: Set breakpoints and trace through a request
3. **Customize the models**: Modify `anomaly_model/model.py` and retrain
4. **Add real agent integration**: Replace mock tools in `agent_harness/`
5. **Build a dashboard**: Use the `/traces` and `/stats` endpoints

Happy debugging! 🚀
