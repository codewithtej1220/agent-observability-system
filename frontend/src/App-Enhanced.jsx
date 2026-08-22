import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Toaster, toast } from 'react-hot-toast';
import { 
  Activity, AlertTriangle, TrendingUp, Eye, 
  Zap, Shield, RefreshCw, CheckCircle, Bell 
} from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, LineChart, Line } from 'recharts';
import { motion } from 'framer-motion';
import TraceModal from './components/TraceModal';
import FilterBar from './components/FilterBar';
import SystemHealth from './components/SystemHealth';
import './App.css';

const API_BASE = 'http://localhost:8001';
const API_KEY = 'dev-key-12345';

axios.defaults.headers.common['X-API-Key'] = API_KEY;

function App() {
  const [stats, setStats] = useState({
    total_traces: 0,
    anomalous_traces: 0,
    avg_combined_score: 0
  });
  const [traces, setTraces] = useState([]);
  const [filteredTraces, setFilteredTraces] = useState([]);
  const [apiStatus, setApiStatus] = useState('checking');
  const [chartData, setChartData] = useState([]);
  const [sparklineData, setSparklineData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedTrace, setSelectedTrace] = useState(null);
  const [filters, setFilters] = useState({
    search: '',
    status: 'all',
    timeRange: '24h'
  });

  useEffect(() => {
    checkApiStatus();
    fetchData();
    
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    applyFilters();
  }, [traces, filters]);

  const checkApiStatus = async () => {
    try {
      const response = await axios.get(`${API_BASE}/health`);
      setApiStatus(response.status === 200 ? 'online' : 'offline');
    } catch (error) {
      setApiStatus('offline');
      toast.error('API is offline');
    }
  };

  const fetchData = async () => {
    try {
      const [statsRes, tracesRes] = await Promise.all([
        axios.get(`${API_BASE}/stats`),
        axios.get(`${API_BASE}/traces?limit=50`)
      ]);
      
      setStats(statsRes.data);
      setTraces(tracesRes.data);
      
      // Generate chart data
      const chartPoints = tracesRes.data.slice(0, 20).reverse().map((trace, idx) => ({
        name: `T${idx + 1}`,
        score: (trace.combined_score * 100).toFixed(1),
        anomalous: trace.is_anomalous ? 100 : 0
      }));
      setChartData(chartPoints);

      // Generate sparkline data (last 30 traces)
      const sparkline = tracesRes.data.slice(0, 30).reverse().map((trace, idx) => ({
        x: idx,
        y: trace.is_anomalous ? 1 : 0
      }));
      setSparklineData(sparkline);
      
      setLoading(false);
    } catch (error) {
      console.error('Error fetching data:', error);
      toast.error('Failed to fetch data');
      setLoading(false);
    }
  };

  const applyFilters = () => {
    let filtered = [...traces];

    // Search filter
    if (filters.search) {
      filtered = filtered.filter(trace =>
        trace.trace_id?.toLowerCase().includes(filters.search.toLowerCase()) ||
        trace.task_description?.toLowerCase().includes(filters.search.toLowerCase())
      );
    }

    // Status filter
    if (filters.status !== 'all') {
      filtered = filtered.filter(trace =>
        filters.status === 'anomalous' ? trace.is_anomalous : !trace.is_anomalous
      );
    }

    setFilteredTraces(filtered);
  };

  const handleFilterChange = (newFilters) => {
    setFilters(prev => ({ ...prev, ...newFilters }));
  };

  const handleExport = () => {
    const dataStr = JSON.stringify(filteredTraces, null, 2);
    const dataBlob = new Blob([dataStr], { type: 'application/json' });
    const url = URL.createObjectURL(dataBlob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `traces-${Date.now()}.json`;
    link.click();
    toast.success('Traces exported successfully');
  };

  const anomalyRate = stats.total_traces > 0 
    ? ((stats.anomalous_traces / stats.total_traces) * 100).toFixed(1)
    : 0;

  const healthyTraces = stats.total_traces - stats.anomalous_traces;

  return (
    <div className="app">
      <Toaster 
        position="top-right"
        toastOptions={{
          style: {
            background: '#1e293b',
            color: '#e2e8f0',
            border: '1px solid rgba(100, 116, 139, 0.3)',
          },
          success: {
            iconTheme: {
              primary: '#10b981',
              secondary: '#1e293b',
            },
          },
          error: {
            iconTheme: {
              primary: '#ef4444',
              secondary: '#1e293b',
            },
          },
        }}
      />

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
          
          <div className="header-actions">
            <button 
              className="notification-btn"
              onClick={() => toast('No new notifications', { icon: '🔔' })}
            >
              <Bell size={20} />
              <span className="notification-badge">0</span>
            </button>
            
            <div className={`status-indicator ${apiStatus === 'online' ? 'online' : 'offline'}`}>
              <div className="status-dot"></div>
              <span>{apiStatus === 'online' ? 'System Online' : 'System Offline'}</span>
            </div>
          </div>
        </div>
      </header>

      {loading ? (
        <div className="loading">
          <div className="spinner"></div>
        </div>
      ) : (
        <div className="container">
          {/* System Health */}
          <SystemHealth stats={stats} />

          {/* Stats Grid */}
          <div className="stats-grid">
            <motion.div 
              className="stat-card"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3 }}
            >
              <div className="stat-header">
                <div className="stat-icon primary">
                  <Activity />
                </div>
                <div className="stat-trend up">Live</div>
              </div>
              <div className="stat-label">Total Traces</div>
              <div className="stat-value">{stats.total_traces}</div>
              
              {/* Mini sparkline */}
              <div className="mini-sparkline">
                <ResponsiveContainer width="100%" height={40}>
                  <LineChart data={sparklineData}>
                    <Line 
                      type="monotone" 
                      dataKey="y" 
                      stroke="#818cf8" 
                      strokeWidth={2}
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </motion.div>

            <motion.div 
              className="stat-card"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.1 }}
            >
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
              
              <div className="progress-bar">
                <div 
                  className="progress-fill danger"
                  style={{ width: `${anomalyRate}%` }}
                ></div>
              </div>
            </motion.div>

            <motion.div 
              className="stat-card"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.2 }}
            >
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
              
              <div className="progress-bar">
                <div 
                  className="progress-fill success"
                  style={{ width: `${100 - anomalyRate}%` }}
                ></div>
              </div>
            </motion.div>

            <motion.div 
              className="stat-card"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.3 }}
            >
              <div className="stat-header">
                <div className="stat-icon warning">
                  <TrendingUp />
                </div>
              </div>
              <div className="stat-label">Avg Anomaly Score</div>
              <div className="stat-value">
                {(stats.avg_combined_score * 100).toFixed(1)}%
              </div>
              
              <div className="stat-change positive">
                <span>↓ 12% from last hour</span>
              </div>
            </motion.div>
          </div>

          {/* Chart */}
          <motion.div 
            className="chart-container"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: 0.4 }}
          >
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
          </motion.div>

          {/* Filter Bar */}
          <FilterBar 
            onFilterChange={handleFilterChange}
            onExport={handleExport}
          />

          {/* Recent Traces */}
          <motion.div 
            className="traces-container"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: 0.5 }}
          >
            <div className="chart-header" style={{ marginBottom: '1.5rem' }}>
              <h2 className="chart-title">
                <Eye style={{ display: 'inline', marginRight: '0.5rem' }} />
                Recent Traces ({filteredTraces.length})
              </h2>
              <button className="filter-btn" onClick={fetchData}>
                <RefreshCw size={16} style={{ marginRight: '0.5rem' }} />
                Refresh
              </button>
            </div>
            
            {filteredTraces.length === 0 ? (
              <div className="empty-state">
                <AlertTriangle size={48} />
                <h3>No traces found</h3>
                <p>Try adjusting your filters</p>
              </div>
            ) : (
              filteredTraces.slice(0, 10).map((trace, idx) => (
                <motion.div 
                  key={idx} 
                  className="trace-item"
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.3, delay: idx * 0.05 }}
                  onClick={() => setSelectedTrace(trace)}
                  style={{ cursor: 'pointer' }}
                >
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
                </motion.div>
              ))
            )}
          </motion.div>
        </div>
      )}

      {/* Trace Detail Modal */}
      {selectedTrace && (
        <TraceModal 
          trace={selectedTrace}
          onClose={() => setSelectedTrace(null)}
        />
      )}
    </div>
  );
}

export default App;
