# 🚀 Quick Start Guide - Agent Observability Dashboard

## 📋 Prerequisites

- Python 3.10+
- Node.js 16+ and npm
- PostgreSQL (or Supabase account)
- Git

---

## ⚡ 5-Minute Setup

### 1. **Clone Repository**
```bash
cd C:\Users\bhanu\Downloads\project1-agent-observability\project1-agent-observability
```

### 2. **Backend Setup**
```bash
# Install Python dependencies
pip install -r requirements.txt

# Set environment variables (create .env file)
# Copy from .env.example and fill in your Supabase credentials
DATABASE_URL=postgresql://user:pass@host:port/dbname
SENTRY_DSN=your_sentry_dsn_here
API_KEY=dev-key-12345
```

### 3. **Frontend Setup**
```bash
cd frontend
npm install
```

---

## 🎬 Running the Application

### **Terminal 1 - Backend API**
```bash
# From project root
python -m uvicorn api.main:app --reload --port 8001
```

**Expected Output:**
```
INFO:     Uvicorn running on http://127.0.0.1:8001
INFO:     Application startup complete.
```

### **Terminal 2 - Frontend**
```bash
# From frontend directory
cd frontend
npm start
```

**Expected Output:**
```
Compiled successfully!
You can now view agent-observability-dashboard in the browser.
  Local:            http://localhost:3000
```

---

## 🌐 Access the Dashboard

Open your browser and navigate to:
```
http://localhost:3000
```

You should see:
- ✅ Header with "Agent Observability" branding
- ✅ System Health cards with animated count-ups
- ✅ **3D Radar HUD Visualization** (the new feature!)
  - Blue glowing nodes (normal traces)
  - Orange/papaya nodes (anomalies)
  - Rotating sweep animation
  - HUD corner brackets
  - Real-time readouts
- ✅ Statistics grid with progress bars
- ✅ Real-time anomaly chart
- ✅ Recent traces list

---

## 🎮 Interacting with the 3D Visualization

| Action | How To |
|--------|--------|
| **Manual Rotation** | Click and drag anywhere in the 3D view |
| **Toggle Auto-Rotate** | Click the `[Rotate]` button in the top-right |
| **View Details** | Click on any trace in the "Recent Traces" list |
| **Export Data** | Click the "Export" button in the filter bar |
| **Refresh** | Click the "Refresh" button or wait for auto-update (every 5s) |

---

## 🔍 What to Look For

### **HUD Overlay (New!)**
- **Top-left**: `NODES 42` (total traces visualized)
- **Top-right**: `ANOMALY 5` (anomalous traces detected, in orange)
- **Bottom-left**: `SCAN 00:03:24` (elapsed time)
- **Corners**: Blue bracket decorations
- **Center**: Rotating sweep line (completes every 4.5 seconds)

### **Node Colors**
- 🔵 **Blue glow** = Normal trace
- 🟠 **Orange/papaya glow** = Anomalous trace (with pulsating rings)
- Lines between nodes = Relationships (colored by connected node types)

### **Animations**
- **Count-up**: System Health numbers smoothly animate from 0
- **Pulse**: Anomalous nodes expand/contract rhythmically
- **Sweep**: Radar line rotates continuously
- **Rings**: Expanding detection circles around anomalies
- **Drag**: Camera movement has smooth momentum

---

## 📊 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Check API status |
| `/stats` | GET | Get overall statistics |
| `/traces?limit=50` | GET | Fetch recent traces |
| `/traces/{trace_id}` | GET | Get specific trace details |

**Authentication**: Include `X-API-Key: dev-key-12345` header

---

## 🐛 Troubleshooting

### **Backend not starting?**
```bash
# Check Python version
python --version  # Should be 3.10+

# Check if port 8001 is available
netstat -ano | findstr :8001

# Verify environment variables
cat .env
```

### **Frontend not loading?**
```bash
# Clear cache and reinstall
cd frontend
rm -rf node_modules package-lock.json
npm install
npm start
```

### **3D visualization not rendering?**
- Check browser console (F12) for errors
- Ensure Three.js is loaded: `npm list three`
- Try a different browser (Chrome/Edge recommended)
- Disable browser extensions that might block WebGL

### **CORS errors?**
- Backend should have CORS enabled in `api/main.py`
- Check that frontend is running on port 3000
- Verify API_BASE in `frontend/src/App.jsx` is `http://localhost:8001`

---

## 📦 Project Structure

```
project1-agent-observability/
├── api/                    # FastAPI backend
│   ├── main.py            # API entry point
│   ├── database.py        # PostgreSQL connection
│   ├── auth.py            # API key authentication
│   └── ...
├── frontend/              # React dashboard
│   ├── src/
│   │   ├── components/
│   │   │   ├── ThreeDVisualization.jsx  # 🌟 NEW RADAR HUD
│   │   │   ├── SystemHealth.jsx         # 🌟 GSAP animations
│   │   │   └── ...
│   │   ├── hooks/
│   │   │   └── useCountUp.js            # 🌟 NEW animation hook
│   │   ├── App.jsx
│   │   └── App.css                      # 🌟 Enhanced styling
│   └── package.json
├── data/                  # Real trace data
├── scripts/               # Training pipeline
├── requirements.txt       # Python dependencies
├── .env                   # Environment variables
├── INTEGRATION_SUMMARY.md # 📖 Integration details
├── VISUAL_FEATURES.md     # 📖 Visual guide
└── README.md              # Main documentation
```

---

## 🎨 Customization

### **Change Color Scheme**
Edit `frontend/src/App.css`:
```css
:root {
  --papaya: #ff7a1a;  /* Anomaly color */
  --signal: #5b8cff;  /* Normal color */
  --mint: #2ee6a6;    /* Success color */
}
```

### **Adjust Animation Speed**
Edit `frontend/src/components/ThreeDVisualization.jsx`:
```javascript
// Line ~150: Sweep animation duration
animation: sweep 4.5s linear infinite;  /* Change 4.5s */

// Line ~180: Pulse speed
const s = node.baseScale + Math.sin(t * 2.4 + node.phase) * 0.35;  /* Change 2.4 */
```

### **Change Node Count**
Edit `frontend/src/components/ThreeDVisualization.jsx`:
```javascript
// Line ~120
const nodeCount = Math.min(traces.length, 42);  /* Change 42 */
```

---

## 🔧 Development Tips

### **Hot Reload**
Both backend and frontend support hot reload:
- Backend: `--reload` flag in uvicorn
- Frontend: Webpack dev server watches for changes

### **Debugging**
```javascript
// In ThreeDVisualization.jsx, add:
console.log('Nodes:', particlesRef.current.length);
console.log('Anomalies:', hudStats.anomalies);
```

### **Performance Monitoring**
Open browser DevTools (F12) → Performance tab → Record while interacting

---

## 📈 Next Steps

1. ✅ **Run the application** - See it in action!
2. 📖 **Read VISUAL_FEATURES.md** - Understand what you're seeing
3. 🔧 **Customize colors/animations** - Make it your own
4. 🚀 **Deploy to production** - Share with your team
5. 🎓 **Explore the code** - Learn how it works

---

## 🆘 Need Help?

- **GitHub Issues**: https://github.com/codewithtej1220/agent-observability-system/issues
- **Documentation**: Read INTEGRATION_SUMMARY.md for technical details
- **Visual Guide**: Read VISUAL_FEATURES.md for UI details

---

## ✅ Success Checklist

After following this guide, you should have:

- [x] Backend API running on port 8001
- [x] Frontend dashboard running on port 3000
- [x] 3D radar HUD visualization visible
- [x] Blue and orange glowing nodes
- [x] Rotating sweep animation
- [x] HUD readouts updating
- [x] System Health stats counting up
- [x] Drag-to-orbit camera control working
- [x] Real-time data refreshing every 5 seconds

---

**Enjoy your production-grade AI observability dashboard!** 🎉

*Last Updated: January 2025*
*Version: 2.0 (Radar HUD Edition)*
