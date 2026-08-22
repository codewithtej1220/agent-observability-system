import React from 'react';
import { Server, Cpu, Database, Zap } from 'lucide-react';
import './SystemHealth.css';

const SystemHealth = ({ stats }) => {
  const uptime = '99.9%'; // Calculate from API
  const latency = '45ms'; // Get from API
  const throughput = '1.2k/min'; // Calculate from traces
  
  return (
    <div className="system-health">
      <h3 className="health-title">System Health</h3>
      
      <div className="health-grid">
        <div className="health-item">
          <div className="health-icon server">
            <Server size={20} />
          </div>
          <div className="health-content">
            <div className="health-label">Uptime</div>
            <div className="health-value">{uptime}</div>
          </div>
        </div>

        <div className="health-item">
          <div className="health-icon cpu">
            <Zap size={20} />
          </div>
          <div className="health-content">
            <div className="health-label">Latency</div>
            <div className="health-value">{latency}</div>
          </div>
        </div>

        <div className="health-item">
          <div className="health-icon database">
            <Database size={20} />
          </div>
          <div className="health-content">
            <div className="health-label">DB Status</div>
            <div className="health-value health-online">Online</div>
          </div>
        </div>

        <div className="health-item">
          <div className="health-icon throughput">
            <Cpu size={20} />
          </div>
          <div className="health-content">
            <div className="health-label">Throughput</div>
            <div className="health-value">{throughput}</div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default SystemHealth;
