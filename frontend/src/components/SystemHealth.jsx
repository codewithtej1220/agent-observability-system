import React from 'react';
import { Server, Cpu, Database, Zap } from 'lucide-react';
import { useCountUpFloat } from '../hooks/useCountUp';
import './SystemHealth.css';

const SystemHealth = ({ stats }) => {
  const uptimeRef = useCountUpFloat(99.9, 1, '%');
  const latencyRef = useCountUpFloat(45, 0, 'ms');
  const throughputRef = useCountUpFloat(1.2, 1, 'k/min');
  
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
            <div className="health-value" ref={uptimeRef}>0%</div>
          </div>
        </div>

        <div className="health-item">
          <div className="health-icon cpu">
            <Zap size={20} />
          </div>
          <div className="health-content">
            <div className="health-label">Latency</div>
            <div className="health-value" ref={latencyRef}>0ms</div>
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
            <div className="health-value" ref={throughputRef}>0k/min</div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default SystemHealth;
