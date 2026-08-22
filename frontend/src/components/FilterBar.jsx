import React from 'react';
import { Search, Filter, Download, Calendar } from 'lucide-react';
import './FilterBar.css';

const FilterBar = ({ onFilterChange, onExport }) => {
  return (
    <div className="filter-bar">
      <div className="search-box">
        <Search size={18} />
        <input
          type="text"
          placeholder="Search traces by ID or description..."
          onChange={(e) => onFilterChange({ search: e.target.value })}
        />
      </div>

      <div className="filter-controls">
        <select
          className="filter-select"
          onChange={(e) => onFilterChange({ status: e.target.value })}
        >
          <option value="all">All Traces</option>
          <option value="anomalous">Anomalous Only</option>
          <option value="normal">Normal Only</option>
        </select>

        <select
          className="filter-select"
          onChange={(e) => onFilterChange({ timeRange: e.target.value })}
        >
          <option value="1h">Last Hour</option>
          <option value="24h">Last 24 Hours</option>
          <option value="7d">Last 7 Days</option>
          <option value="30d">Last 30 Days</option>
        </select>

        <button className="filter-btn export" onClick={onExport}>
          <Download size={16} />
          Export
        </button>
      </div>
    </div>
  );
};

export default FilterBar;
