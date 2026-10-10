import { createContext, useContext, useState } from "react";
import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import { useApi } from "./api";
import { RANGES, Segmented } from "./components/ui";
import Overview from "./pages/Overview";
import Runs from "./pages/Runs";
import RunDetail from "./pages/RunDetail";
import Agents from "./pages/Agents";
import AgentDetail from "./pages/AgentDetail";
import Compare from "./pages/Compare";
import Review from "./pages/Review";
import Models from "./pages/Models";
import Policy from "./pages/Policy";

const RangeContext = createContext({ hours: 24, setHours: () => {} });
export const useRange = () => useContext(RangeContext);

const NAV = [
  { to: "/", label: "Overview", end: true },
  { to: "/runs", label: "Runs" },
  { to: "/agents", label: "Agents" },
  { to: "/review", label: "Review queue", badge: "pending_review" },
  { to: "/models", label: "Detection models" },
  { to: "/policy", label: "Intervention policy" },
];

const TITLES = {
  "": "Overview", runs: "Runs", agents: "Agents", compare: "Agent comparison",
  review: "Review queue", models: "Detection models", policy: "Intervention policy",
};

// Pages whose content depends on the global time range.
const RANGED = new Set(["", "agents", "compare"]);

export default function App() {
  const [hours, setHours] = useState(24);
  const meta = useApi("/api/meta", { refreshMs: 30000 });
  const queue = useApi("/api/review-queue?limit=1", { refreshMs: 30000 });
  const loc = useLocation();
  const section = loc.pathname.split("/")[1] || "";
  const counts = { pending_review: queue.data?.total };

  return (
    <RangeContext.Provider value={{ hours, setHours }}>
      <div className="app">
        <aside className="sidebar">
          <div className="brand">
            <div className="brand-title">Agent Observability</div>
            <div className="brand-sub">Silent-failure detection</div>
          </div>
          <nav className="nav">
            {NAV.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.end}>
                <span>{n.label}</span>
                {n.badge && counts[n.badge] ? <span className="count">{counts[n.badge]}</span> : null}
              </NavLink>
            ))}
          </nav>
          <div className="sidebar-foot">
            {meta.data ? (
              <>
                <div>Model {meta.data.model_version || "not trained"}{meta.data.retraining ? " · retraining…" : ""}</div>
                <div>{meta.data.agents.length} agents monitored</div>
              </>
            ) : meta.error ? "API unreachable" : "Connecting…"}
          </div>
        </aside>
        <div className="main">
          <header className="topbar">
            <div className="crumbs">{TITLES[section] ?? ""}</div>
            {RANGED.has(section) && (
              <Segmented options={RANGES} value={hours} onChange={setHours} />
            )}
          </header>
          <main className="content">
            <Routes>
              <Route path="/" element={<Overview />} />
              <Route path="/runs" element={<Runs />} />
              <Route path="/runs/:id" element={<RunDetail meta={meta.data} />} />
              <Route path="/agents" element={<Agents />} />
              <Route path="/agents/:id" element={<AgentDetail />} />
              <Route path="/compare" element={<Compare />} />
              <Route path="/review" element={<Review />} />
              <Route path="/models" element={<Models meta={meta.data} />} />
              <Route path="/policy" element={<Policy />} />
              <Route path="*" element={<div className="empty">Page not found.</div>} />
            </Routes>
          </main>
        </div>
      </div>
    </RangeContext.Provider>
  );
}
