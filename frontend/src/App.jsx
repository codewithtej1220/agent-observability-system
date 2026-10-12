import { createContext, useContext, useState } from "react";
import { Navigate, NavLink, Route, Routes, useLocation } from "react-router-dom";
import { useApi } from "./api";
import { useAuth } from "./auth";
import { Loading, RANGES, Segmented } from "./components/ui";
import Overview from "./pages/Overview";
import Runs from "./pages/Runs";
import RunDetail from "./pages/RunDetail";
import Agents from "./pages/Agents";
import AgentDetail from "./pages/AgentDetail";
import Compare from "./pages/Compare";
import Review from "./pages/Review";
import Models from "./pages/Models";
import Policy from "./pages/Policy";
import Settings from "./pages/Settings";
import { AuthPage } from "./pages/Login";
import LLMOverview from "./pages/llm/LLMOverview";
import { LLMCallDetail, LLMCalls } from "./pages/llm/LLMCalls";
import Contracts from "./pages/llm/Contracts";
import Alerts from "./pages/llm/Alerts";
import DriftTests from "./pages/llm/DriftTests";
import Connect from "./pages/llm/Connect";

const RangeContext = createContext({ hours: 24, setHours: () => {} });
export const useRange = () => useContext(RangeContext);

const NAV = [
  { group: "LLM monitoring" },
  { to: "/", label: "Overview", end: true },
  { to: "/llm/calls", label: "Live calls" },
  { to: "/llm/contracts", label: "Prompt contracts" },
  { to: "/llm/alerts", label: "Alerts", badge: "alerts" },
  { to: "/llm/drift", label: "Drift tests" },
  { to: "/llm/connect", label: "Connect LLMs" },
  { group: "Agent monitoring" },
  { to: "/agent-overview", label: "Agent overview" },
  { to: "/runs", label: "Runs" },
  { to: "/agents", label: "Agents" },
  { to: "/review", label: "Review queue", badge: "review" },
  { to: "/models", label: "Detection models" },
  { to: "/policy", label: "Intervention policy" },
  { group: "Workspace" },
  { to: "/settings", label: "Settings" },
];

const TITLES = {
  "": "LLM overview", llm: "LLM monitoring", "agent-overview": "Agent overview", runs: "Runs", agents: "Agents",
  compare: "Agent comparison", review: "Review queue", models: "Detection models", policy: "Intervention policy", settings: "Settings",
};
const RANGED = new Set(["", "agent-overview", "agents", "compare"]);

export default function App() {
  const auth = useAuth();
  const loc = useLocation();
  if (auth.loading) return <Loading />;
  if (!auth.me) {
    return (
      <Routes>
        <Route path="/signup" element={<AuthPage mode="signup" />} />
        <Route path="/login" element={<AuthPage mode="login" />} />
        <Route path="*" element={<Navigate to="/login" replace state={{ from: loc.pathname }} />} />
      </Routes>
    );
  }
  return <Shell />;
}

function Shell() {
  const { user, workspace, workspaces, switchWorkspace, logout } = useAuth();
  const [hours, setHours] = useState(24);
  const meta = useApi("/api/meta", { refreshMs: 30000 });
  const queue = useApi("/api/review-queue?limit=1", { refreshMs: 30000 });
  const alerts = useApi("/api/llm/alerts?status=open&limit=100", { refreshMs: 15000 });
  const loc = useLocation();
  const section = loc.pathname.split("/")[1] || "";
  const counts = { review: queue.data?.total, alerts: alerts.data?.length };
  const showRange = RANGED.has(section);

  return (
    <RangeContext.Provider value={{ hours, setHours }}>
      <div className="app">
        <aside className="sidebar">
          <div className="brand">
            <div className="brand-title">Agent Observability</div>
            <div className="brand-sub">LLM and agent monitoring</div>
          </div>
          <nav className="nav">
            {NAV.map((n) => n.group ? <div key={n.group} className="nav-group">{n.group}</div> : (
              <NavLink key={n.to} to={n.to} end={n.end}>
                <span>{n.label}</span>
                {n.badge && counts[n.badge] ? <span className="count">{counts[n.badge]}</span> : null}
              </NavLink>
            ))}
          </nav>
          <div className="sidebar-foot">
            <div style={{ color: "#e6e8eb" }} className="truncate" title={user.email}>{user.name || user.email}</div>
            {workspaces.length > 1 ? (
              <select value={workspace.id} onChange={(e) => switchWorkspace(e.target.value)} aria-label="Workspace">
                {workspaces.map((w) => <option key={w.id} value={w.id}>{w.name} ({w.role})</option>)}
              </select>
            ) : <div className="small">{workspace.name} · {workspace.role}</div>}
            <div className="spread small" style={{ marginBottom: 12 }}>
              <span>Model {meta.data?.model_version || "–"}</span>
              <button className="link-btn" onClick={logout}>Sign out</button>
            </div>
          </div>
        </aside>
        <div className="main">
          <header className="topbar">
            <div className="crumbs">{TITLES[section] ?? ""}</div>
            {showRange && <Segmented options={RANGES} value={hours} onChange={setHours} />}
          </header>
          <main className="content">
            <Routes>
              <Route path="/" element={<LLMOverview />} />
              <Route path="/llm/calls" element={<LLMCalls />} />
              <Route path="/llm/calls/:id" element={<LLMCallDetail />} />
              <Route path="/llm/contracts" element={<Contracts />} />
              <Route path="/llm/alerts" element={<Alerts />} />
              <Route path="/llm/drift" element={<DriftTests />} />
              <Route path="/llm/connect" element={<Connect />} />
              <Route path="/agent-overview" element={<Overview />} />
              <Route path="/runs" element={<Runs />} />
              <Route path="/runs/:id" element={<RunDetail meta={meta.data} />} />
              <Route path="/agents" element={<Agents />} />
              <Route path="/agents/:id" element={<AgentDetail />} />
              <Route path="/compare" element={<Compare />} />
              <Route path="/review" element={<Review />} />
              <Route path="/models" element={<Models meta={meta.data} />} />
              <Route path="/policy" element={<Policy />} />
              <Route path="/settings" element={<Settings />} />
              <Route path="/login" element={<Navigate to="/" replace />} />
              <Route path="/signup" element={<Navigate to="/" replace />} />
              <Route path="*" element={<div className="empty">Page not found.</div>} />
            </Routes>
          </main>
        </div>
      </div>
    </RangeContext.Provider>
  );
}
