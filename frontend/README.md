# Agent Observability Dashboard - Professional React Frontend

Modern, professional dashboard for AI agent monitoring with real-time updates.

## Features

- 🎨 **Professional Dark Theme** - Sleek gradient UI with glassmorphism
- 📊 **Real-Time Charts** - Live anomaly score visualization
- 🔄 **Auto-Refresh** - Updates every 5 seconds
- 📱 **Responsive Design** - Works on all devices
- ⚡ **Fast & Smooth** - React 18 with optimized rendering
- 🎭 **Animations** - Subtle transitions and effects

## Quick Start

```bash
# Install dependencies
cd frontend
npm install

# Start development server
npm start

# Build for production
npm build
```

Dashboard will open at: http://localhost:3000

## What You'll See

### Header
- Logo with gradient effect
- System status indicator (real-time)

### Statistics Cards (4 cards)
1. **Total Traces** - Live count
2. **Anomalies Detected** - With percentage badge
3. **Healthy Traces** - Success rate
4. **Avg Anomaly Score** - Overall system health

### Real-Time Chart
- Area chart showing last 10 traces
- Anomaly scores over time
- Interactive tooltips
- Time range filters (1H/24H/7D)

### Recent Traces List
- Last 10 traces with details
- Color-coded badges (anomalous/normal)
- Trace ID, score, action, steps count
- Refresh button

## Tech Stack

- **React 18** - Latest React with concurrent features
- **Recharts** - Professional charts
- **Lucide React** - Beautiful icons
- **Axios** - API calls
- **Framer Motion** - Smooth animations

## API Integration

Connects to backend at `http://localhost:8000`:
- `/stats` - System statistics
- `/traces` - Recent traces
- `/health` - API status check

## Customization

### Colors
Edit `src/App.css`:
- Primary: `#6366f1` (Indigo)
- Success: `#10b981` (Emerald)
- Danger: `#ef4444` (Red)
- Warning: `#f59e0b` (Amber)

### Chart Data
Modify `chartData` in `App.jsx` to change visualization.

### Refresh Interval
Change line in `App.jsx`:
```javascript
const interval = setInterval(fetchData, 5000); // 5000ms = 5 seconds
```

## Production Build

```bash
npm run build
```

Outputs to `build/` directory. Serve with any static file server.

## Screenshots

```
┌─────────────────────────────────────────────────────────────┐
│  🛡️ Agent Observability                    ● System Online │
│  AI Silent Failure Detection System                         │
└─────────────────────────────────────────────────────────────┘

┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────┐
│ 📊 Total     │ │ ⚠️ Anomalies │ │ ✅ Healthy   │ │ 📈 Avg   │
│ Traces       │ │ Detected     │ │ Traces       │ │ Score    │
│              │ │              │ │              │ │          │
│ 125          │ │ 23           │ │ 102          │ │ 67.3%    │
└──────────────┘ └──────────────┘ └──────────────┘ └──────────┘

┌─────────────────────────────────────────────────────────────┐
│ ⚡ Real-Time Anomaly Scores      [1H] [24H] [7D]            │
│                                                              │
│  [Area Chart with gradient fill showing scores over time]   │
│                                                              │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ 👁️ Recent Traces                                  🔄 Refresh │
│                                                              │
│ ┌─────────────────────────────────────────────── ⚠️ Anomalous│
│ │ Search for weather in Seattle...                          │
│ │ ID: abc123...                                             │
│ │ Score: 85.3% | Action: interrupt | Steps: 12             │
│ └───────────────────────────────────────────────────────────│
│                                                              │
│ [More traces...]                                             │
└─────────────────────────────────────────────────────────────┘
```

## Professional Features

✅ Glassmorphism effects
✅ Gradient text and backgrounds
✅ Smooth hover animations
✅ Responsive grid layouts
✅ Custom scrollbars
✅ Live status indicators
✅ Color-coded metrics
✅ Professional typography
✅ Dark mode optimized

Perfect for production deployments! 🚀
