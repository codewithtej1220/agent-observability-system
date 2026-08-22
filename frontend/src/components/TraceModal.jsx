import React from 'react';
import { X, Clock, Activity, TrendingUp, Zap, AlertTriangle } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import './TraceModal.css';

const TraceModal = ({ trace, onClose }) => {
  if (!trace) return null;

  return (
    <AnimatePresence>
      <motion.div
        className="modal-overlay"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
      >
        <motion.div
          className="modal-content"
          initial={{ scale: 0.9, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          exit={{ scale: 0.9, opacity: 0 }}
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="modal-header">
            <div>
              <h2 className="modal-title">Trace Details</h2>
              <p className="modal-subtitle">ID: {trace.trace_id}</p>
            </div>
            <button className="modal-close" onClick={onClose}>
              <X size={20} />
            </button>
          </div>

          {/* Status Badge */}
          <div className={`modal-status ${trace.is_anomalous ? 'anomalous' : 'normal'}`}>
            {trace.is_anomalous ? (
              <>
                <AlertTriangle size={16} />
                <span>Anomalous Behavior Detected</span>
              </>
            ) : (
              <>
                <Activity size={16} />
                <span>Normal Execution</span>
              </>
            )}
          </div>

          {/* Metrics Grid */}
          <div className="modal-metrics">
            <div className="modal-metric">
              <div className="metric-icon score">
                <TrendingUp size={20} />
              </div>
              <div className="metric-content">
                <div className="metric-label">Anomaly Score</div>
                <div className="metric-value">{(trace.combined_score * 100).toFixed(2)}%</div>
              </div>
            </div>

            <div className="modal-metric">
              <div className="metric-icon action">
                <Zap size={20} />
              </div>
              <div className="metric-content">
                <div className="metric-label">Recommended Action</div>
                <div className="metric-value">{trace.policy_action || 'Continue'}</div>
              </div>
            </div>

            <div className="modal-metric">
              <div className="metric-icon time">
                <Clock size={20} />
              </div>
              <div className="metric-content">
                <div className="metric-label">Timestamp</div>
                <div className="metric-value">
                  {new Date(trace.created_at * 1000).toLocaleString()}
                </div>
              </div>
            </div>
          </div>

          {/* Task Description */}
          <div className="modal-section">
            <h3 className="section-title">Task Description</h3>
            <div className="section-content">
              {trace.task_description || 'No description provided'}
            </div>
          </div>

          {/* Context Summary */}
          {trace.context_summary && (
            <div className="modal-section">
              <h3 className="section-title">Context Vector</h3>
              <div className="context-grid">
                {trace.context_summary.map((value, idx) => (
                  <div key={idx} className="context-item">
                    <span className="context-label">Feature {idx + 1}</span>
                    <span className="context-value">{value.toFixed(4)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Actions */}
          <div className="modal-actions">
            <button className="btn btn-secondary" onClick={onClose}>
              Close
            </button>
            <button className="btn btn-primary">
              Export Trace
            </button>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
};

export default TraceModal;
