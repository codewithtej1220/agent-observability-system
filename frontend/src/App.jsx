import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { 
  Activity, AlertTriangle, TrendingUp, Eye, 
  Zap, Shield, RefreshCw, CheckCircle 
} from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import './App.css';

const API_BASE = 'http://localhost:8001';
const API_KEY = 'dev-key-12345'; // Development API key

// Configure axios to include API key in all requests
axios.defaults.headers.common['X-API-Key'] = API_KEY;

function App() {
  const [stats, setStats] = useState({
    total_traces: 0,
    anomalous_traces: 0,
    avg_combined_score: 0
  });
  const [traces, setTraces] = useState([]);
  const [apiStatus, setApiStatus] = useState('checking');
  const [chartData, setChartData] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    checkApiStatus();
    fetchData();
    
    // Auto-refresh every 5 seconds
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, []);

  const checkApiStatus = async () => {
    try {
      const response = await axios.get(`${API_BASE}/health`);
      setApiStatus(response.status === 200 ? 'online' : 'offline');
    } catch (error) {
      setApiStatus('offline');
    }
  };

  const fetchData = async () => {
    try {
      const [statsRes, tracesRes] = await Promise.all([
        axios.get(`${API_BASE}/stats`),
        axios.get(`${API_BASE}/traces?limit=10`)
      ]);
      
      setStats(statsRes.data);
      setTraces(tracesRes.data);
      
      // Generate chart data
      const chartPoints = tracesRes.data.slice(0, 10).reverse().map((trace, idx) => ({
        name: `T${idx + 1}`,
        score: (trace.combined_score * 100).toFixed(1),
        anomalous: trace.is_anomalous ? 100 : 0
      }));
      setChartData(chartPoints);
      
      setLoading(false);
    } catch (error) {
      console.error('Error fetching data:', error);
      setLoading(false);
    }
  };

  const anomalyRate = stats.total_traces > 0 
    ? ((stats.anomalous_traces / stats.total_traces) * 100).toFixed(1)
    : 0;

  const healthyTraces = stats.total_traces - stats.anomalous_traces;

  return (
    <div className="app">
      {/* Header */}
      <header className="header">
        <div className="header-content">
          <div className="logo-section">
            <div className="logo-icon">
              <Shield />
            </div>
            <div className="logo-text">
              <h1>Agent Observability</h1>
              <p>AI Silent Failure Detection System</p>
            </div>
          </div>
          
          <div className={`status-indicator ${apiStatus === 'online' ? 'online' : 'offline'}`}>
            <div className="status-dot"></div>
            <span>{apiStatus === 'online' ? 'System Online' : 'System Offline'}</span>
          </div>
        </div>
      </header>

      {loading ? (
        <div className="loading">
          <div className="spinner"></div>
        </div>
      ) : (
        <div className="container">
          {/* Stats Grid */}
          <div className="stats-grid">
            <div className="stat-card">
              <div className="stat-header">
                <div className="stat-icon primary">
                  <Activity />
                </div>
                <div className="stat-trend up">Live</div>
              </div>
              <div className="stat-label">Total Traces</div>
              <div className="stat-value">{stats.total_traces}</div>
            </div>

            <div className="stat-card">
              <div className="stat-header">
                <div className="stat-icon danger">
                  <AlertTriangle />
                </div>
                <div className="stat-trend up">
                  {anomalyRate}%
                </div>
              </div>
              <div className="stat-label">Anomalies Detected</div>
              <div className="stat-value">{stats.anomalous_traces}</div>
            </div>

            <div className="stat-card">
              <div className="stat-header">
                <div className="stat-icon success">
                  <CheckCircle />
                </div>
                <div className="stat-trend down">
                  {(100 - anomalyRate).toFixed(1)}%
                </div>
              </div>
              <div className="stat-label">Healthy Traces</div>
              <div className="stat-value">{healthyTraces}</div>
            </div>

            <div className="stat-card">
              <div className="stat-header">
                <div className="stat-icon warning">
                  <TrendingUp />
                </div>
              </div>
              <div className="stat-label">Avg Anomaly Score</div>
              <div className="stat-value">
                {(stats.avg_combined_score * 100).toFixed(1)}%
              </div>
            </div>
          </div>

          {/* Chart */}
          <div className="chart-container">
            <div className="chart-header">
              <h2 className="chart-title">
                <Zap style={{ display: 'inline', marginRight: '0.5rem' }} />
                Real-Time Anomaly Scores
              </h2>
              <div className="chart-filters">
                <button className="filter-btn active">1H</button>
                <button className="filter-btn">24H</button>
                <button className="filter-btn">7D</button>
              </div>
            </div>
            
            <ResponsiveContainer width="100%" height={300}>
              <AreaChart data={chartData}>
                <defs>
                  <linearGradient id="colorScore" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#6366f1" stopOpacity={0.8}/>
                    <stop offset="95%" stopColor="#6366f1" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="name" stroke="#94a3b8" />
                <YAxis stroke="#94a3b8" />
                <Tooltip 
                  contentStyle={{ 
                    background: '#1e293b', 
                    border: '1px solid #475569',
                    borderRadius: '8px'
                  }} 
                />
                <Legend />
                <Area 
                  type="monotone" 
                  dataKey="score" 
                  stroke="#6366f1" 
                  fillOpacity={1} 
                  fill="url(#colorScore)" 
                  name="Anomaly Score (%)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          {/* Recent Traces */}
          <div className="traces-container">
            <div className="chart-header" style={{ marginBottom: '1.5rem' }}>
              <h2 className="chart-title">
                <Eye style={{ display: 'inline', marginRight: '0.5rem' }} />
                Recent Traces
              </h2>
              <button className="filter-btn" onClick={fetchData}>
                <RefreshCw size={16} style={{ marginRight: '0.5rem' }} />
                Refresh
              </button>
            </div>
            
            {traces.map((trace, idx) => (
              <div key={idx} className="trace-item">
                <div className="trace-header">
                  <div>
                    <div className="trace-title">
                      {trace.task_description ? trace.task_description.substring(0, 60) + '...' : 'No description'}
                    </div>
                    <div className="trace-id">
                      ID: {trace.trace_id || 'Unknown'}
                    </div>
                  </div>
                  <div className={`trace-badge ${trace.is_anomalous ? 'anomalous' : 'normal'}`}>
                    {trace.is_anomalous ? '⚠️ Anomalous' : '✅ Normal'}
                  </div>
                </div>
                
                <div className="trace-details">
                  <div className="trace-detail">
                    <span className="trace-detail-label">Anomaly Score:</span>
                    <span className="trace-detail-value">
                      {(trace.combined_score * 100).toFixed(1)}%
                    </span>
                  </div>
                  <div className="trace-detail">
                    <span className="trace-detail-label">Action:</span>
                    <span className="trace-detail-value">{trace.policy_action || 'N/A'}</span>
                  </div>
                  <div className="trace-detail">
                    <span className="trace-detail-label">Timestamp:</span>
                    <span className="trace-detail-value">
                      {new Date(trace.created_at * 1000).toLocaleTimeString()}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
