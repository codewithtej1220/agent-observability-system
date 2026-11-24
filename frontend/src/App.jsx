import { createContext, useContext, useEffect, useState } from "react";
import { Link, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { useIsFetching } from "@tanstack/react-query";
import * as Menu from "@radix-ui/react-dropdown-menu";
import { Toaster, toast } from "sonner";
import {
  Check, ChevronRight, ChevronsLeft, ChevronsRight, CreditCard, Eye, Info, LogOut, Monitor, Moon, Search, Settings as SettingsIcon, Sun,
} from "lucide-react";
import { useApi } from "./api";
import { useAuth } from "./auth";
import CommandPalette from "./components/CommandPalette";
import { Loading, RANGES, Segmented, Tip } from "./components/ui";
import { ADMIN_NAV, NAV, titleFor } from "./nav";
import { useRealtime } from "./realtime";
import { setThemeMode, useThemeMode } from "./theme";
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
import Admin from "./pages/Admin";
import { PricingPage } from "./pages/Billing";
import { AuthPage } from "./pages/Login";
import LLMOverview from "./pages/llm/LLMOverview";
import { LLMCallDetail, LLMCalls } from "./pages/llm/LLMCalls";
import Contracts from "./pages/llm/Contracts";
import Alerts from "./pages/llm/Alerts";
import DriftTests from "./pages/llm/DriftTests";
import Datasets from "./pages/llm/Datasets";
import Prompts from "./pages/llm/Prompts";
import { SessionDetail, Sessions } from "./pages/llm/Sessions";
import Connect from "./pages/llm/Connect";

const RangeContext = createContext({ hours: 24, setHours: () => {} });
export const useRange = () => useContext(RangeContext);

const RANGED = new Set(["", "agent-overview", "agents", "compare"]);
const COLLAPSE_KEY = "aobs-sidebar-collapsed";

function ThemedToaster() {
  const mode = useThemeMode();
  return <Toaster position="bottom-right" richColors closeButton theme={mode} />;
}

export default function App() {
  const auth = useAuth();
  const loc = useLocation();
  if (auth.loading) return <div className="content"><Loading /></div>;
  if (!auth.me) {
    return (
      <>
        <Routes>
          <Route path="/signup" element={<AuthPage mode="signup" />} />
          <Route path="/login" element={<AuthPage mode="login" />} />
          <Route path="/pricing" element={<PricingPage />} />
          <Route path="*" element={<Navigate to="/login" replace state={{ from: loc.pathname }} />} />
        </Routes>
        <ThemedToaster />
      </>
    );
  }
  return <Shell />;
}

function isActive(item, loc) {
  const [path, query] = item.to.split("?");
  if (query) return loc.pathname === path && loc.search.includes(query);
  if (item.end) return loc.pathname === path;
  if (path === "/settings") return loc.pathname === "/settings" && !/tab=(about|billing)/.test(loc.search);
  return loc.pathname === path || loc.pathname.startsWith(path + "/");
}

function Sidebar({ collapsed, setCollapsed, counts }) {
  const loc = useLocation();
  const { me } = useAuth();
  const groups = me?.is_platform_admin ? [...NAV, ADMIN_NAV] : NAV;
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark"><Eye size={17} /></div>
        <div className="brand-text">
          <div className="brand-title">Agent Observability</div>
          <div className="brand-sub">LLM and agent monitoring</div>
        </div>
      </div>
      <nav className="nav" aria-label="Main">
        {groups.map((g) => (
          <div key={g.group}>
            <div className="nav-group">{g.group}</div>
            {g.items.map((n) => {
              const link = (
                <Link key={n.to} to={n.to} className={isActive(n, loc) ? "active" : ""} aria-current={isActive(n, loc) ? "page" : undefined}>
                  <n.icon size={17} strokeWidth={1.8} />
                  <span className="nav-label">{n.label}</span>
                  {n.badge && counts[n.badge] ? <span className="count">{counts[n.badge]}</span> : null}
                </Link>
              );
              return collapsed ? <Tip key={n.to} label={n.label} side="right">{link}</Tip> : link;
            })}
          </div>
        ))}
      </nav>
      <div style={{ marginTop: "auto" }}>
        <button className="sidebar-collapse icon-btn" onClick={() => setCollapsed(!collapsed)}
                aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}>
          {collapsed ? <ChevronsRight size={16} /> : <ChevronsLeft size={16} />}
        </button>
      </div>
    </aside>
  );
}

function UserMenu() {
  const { user, workspace, workspaces, switchWorkspace, logout } = useAuth();
  const mode = useThemeMode();
  const initials = (user.name || user.email).split(/[\s@.]+/).filter(Boolean).slice(0, 2).map((s) => s[0].toUpperCase()).join("");
  return (
    <Menu.Root>
      <Menu.Trigger asChild>
        <button className="avatar" aria-label="Account menu">{initials}</button>
      </Menu.Trigger>
      <Menu.Portal>
        <Menu.Content className="menu" align="end" sideOffset={8}>
          <div className="menu-head">
            <div><strong>{user.name || user.email}</strong></div>
            <div className="email">{user.email}</div>
          </div>
          <Menu.Separator className="menu-sep" />
          <div className="menu-label">Workspace · {workspace.plan ? workspace.plan[0].toUpperCase() + workspace.plan.slice(1) : "Free"} plan</div>
          {workspaces.map((w) => (
            <Menu.Item key={w.id} className="menu-item" onSelect={() => w.id !== workspace.id && switchWorkspace(w.id)}>
              {w.name} <span className="muted small">{w.role}</span>
              {w.id === workspace.id && <Check size={15} className="menu-check" />}
            </Menu.Item>
          ))}
          <Menu.Separator className="menu-sep" />
          <div className="menu-label">Theme</div>
          {[["system", "System", Monitor], ["light", "Light", Sun], ["dark", "Dark", Moon]].map(([id, label, Icon]) => (
            <Menu.Item key={id} className="menu-item" onSelect={(e) => { e.preventDefault(); setThemeMode(id); }}>
              <Icon size={15} /> {label} {mode === id && <Check size={15} className="menu-check" />}
            </Menu.Item>
          ))}
          <Menu.Separator className="menu-sep" />
          <Menu.Item className="menu-item" asChild><Link to="/settings"><SettingsIcon size={15} /> Settings</Link></Menu.Item>
          <Menu.Item className="menu-item" asChild><Link to="/settings?tab=billing"><CreditCard size={15} /> Plan & billing</Link></Menu.Item>
          <Menu.Item className="menu-item" asChild><Link to="/settings?tab=about"><Info size={15} /> About & how tracking works</Link></Menu.Item>
          <Menu.Item className="menu-item" onSelect={logout}><LogOut size={15} /> Sign out</Menu.Item>
        </Menu.Content>
      </Menu.Portal>
    </Menu.Root>
  );
}

function Shell() {
  const { workspace, logout } = useAuth();
  const [hours, setHours] = useState(24);
  const [palette, setPalette] = useState(false);
  const [collapsed, setCollapsedState] = useState(() => {
    try { return localStorage.getItem(COLLAPSE_KEY) === "1"; } catch { return false; }
  });
  const setCollapsed = (v) => {
    setCollapsedState(v);
    try { localStorage.setItem(COLLAPSE_KEY, v ? "1" : "0"); } catch { /* storage blocked */ }
  };
  const health = useApi("/health", { refreshMs: 30000 });
  const queue = useApi("/api/review-queue?limit=1", { refreshMs: 30000 });
  const alerts = useApi("/api/llm/alerts?status=open&limit=100", { refreshMs: 15000 });
  const fetching = useIsFetching();
  const loc = useLocation();
  const navigate = useNavigate();
  const live = useRealtime(navigate);
  const billing = useApi("/api/billing", { refreshMs: 120000 });

  useEffect(() => {
    const onLimit = (e) => toast.warning(e.detail || "Plan limit reached", {
      id: "plan-limit", action: { label: "View plans", onClick: () => navigate("/settings?tab=billing") },
    });
    window.addEventListener("aobs:plan-limit", onLimit);
    return () => window.removeEventListener("aobs:plan-limit", onLimit);
  }, [navigate]);
  const section = loc.pathname.split("/")[1] || "";
  const counts = { review: queue.data?.total, alerts: alerts.data?.length };
  const crumbs = titleFor(loc.pathname, loc.search);
  const up = !!health.data && !health.error;

  useEffect(() => { window.scrollTo(0, 0); }, [loc.pathname]);

  return (
    <RangeContext.Provider value={{ hours, setHours }}>
      {fetching > 0 && <div className="fetch-bar" aria-hidden="true" />}
      <div className={`app ${collapsed ? "collapsed" : ""}`}>
        <Sidebar collapsed={collapsed} setCollapsed={setCollapsed} counts={counts} />
        <div className="main">
          <header className="topbar">
            <div className="crumbs">
              <span className="truncate" style={{ maxWidth: 160 }}>{workspace.name}</span>
              {crumbs.filter(Boolean).map((c, i, arr) => (
                <span key={c} className="row" style={{ gap: 6, flexWrap: "nowrap" }}>
                  <ChevronRight size={14} />
                  {i === arr.length - 1 ? <strong>{c}</strong> : <span>{c}</span>}
                </span>
              ))}
            </div>
            <div className="topbar-actions">
              {RANGED.has(section) && <Segmented options={RANGES} value={hours} onChange={setHours} />}
              <button className="search-btn" onClick={() => setPalette(true)} aria-label="Search and jump (Ctrl+K)">
                <span className="row" style={{ gap: 8 }}><Search size={15} /><span className="search-label">Search or jump to…</span></span>
                <kbd>Ctrl K</kbd>
              </button>
              <Tip label={{ live: "Live: new calls, alerts and flagged runs appear instantly",
                            connecting: "Connecting to live updates…", offline: "Live updates unavailable; pages refresh periodically" }[live]}>
                <span className="live-pill" role="status">
                  <span className={`live-dot ${live}`} />
                  <span className="live-text">{live === "live" ? "Live" : live === "connecting" ? "Connecting" : "Offline"}</span>
                </span>
              </Tip>
              <Tip label={up ? `API online · model ${health.data.model_version || "–"}` : "API unreachable"}>
                <span className="status-dot" style={{ background: up ? "var(--good)" : "var(--critical)" }} role="status"
                      aria-label={up ? "API online" : "API unreachable"} />
              </Tip>
              <UserMenu />
            </div>
          </header>
          <main className="content">
            <PlanBanner billing={billing.data} />
            <Routes>
              <Route path="/" element={<LLMOverview />} />
              <Route path="/llm/calls" element={<LLMCalls />} />
              <Route path="/llm/calls/:id" element={<LLMCallDetail />} />
              <Route path="/llm/sessions" element={<Sessions />} />
              <Route path="/llm/sessions/:id" element={<SessionDetail />} />
              <Route path="/llm/prompts" element={<Prompts />} />
              <Route path="/llm/datasets" element={<Datasets />} />
              <Route path="/llm/contracts" element={<Contracts />} />
              <Route path="/llm/alerts" element={<Alerts />} />
              <Route path="/llm/drift" element={<DriftTests />} />
              <Route path="/llm/connect" element={<Connect />} />
              <Route path="/agent-overview" element={<Overview />} />
              <Route path="/runs" element={<Runs />} />
              <Route path="/runs/:id" element={<RunDetailRoute />} />
              <Route path="/agents" element={<Agents />} />
              <Route path="/agents/:id" element={<AgentDetail />} />
              <Route path="/compare" element={<Compare />} />
              <Route path="/review" element={<Review />} />
              <Route path="/models" element={<ModelsRoute />} />
              <Route path="/policy" element={<Policy />} />
              <Route path="/settings" element={<Settings />} />
              <Route path="/pricing" element={<Navigate to="/settings?tab=billing" replace />} />
              <Route path="/admin" element={<Admin />} />
              <Route path="/login" element={<Navigate to="/" replace />} />
              <Route path="/signup" element={<Navigate to="/" replace />} />
              <Route path="*" element={<div className="empty">Page not found.</div>} />
            </Routes>
          </main>
        </div>
      </div>
      <CommandPalette open={palette} onOpenChange={setPalette} onSignOut={logout} />
      <ThemedToaster />
    </RangeContext.Provider>
  );
}

/** Shown when the workspace is near or over a monthly limit, or a payment failed. */
function PlanBanner({ billing }) {
  const loc = useLocation();
  if (!billing || loc.search.includes("tab=billing")) return null;
  const { usage, limits, status } = billing;
  const ratio = (k) => (limits[k] ? usage[k] / limits[k] : 0);
  const worst = ratio("llm_calls") >= ratio("agent_runs") ? "llm_calls" : "agent_runs";
  const label = worst === "llm_calls" ? "tracked LLM calls" : "agent runs";
  let msg = null;
  let critical = false;
  if (status === "past_due") {
    msg = "The last payment failed. Update your card to keep paid features.";
    critical = true;
  } else if (ratio(worst) >= 1) {
    msg = worst === "llm_calls"
      ? "This month's tracked-call limit is used up. Calls are still forwarded to the provider but no longer checked."
      : "This month's agent-run limit is used up. New runs are not being analyzed.";
    critical = true;
  } else if (ratio(worst) >= 0.8) {
    msg = `${Math.round(ratio(worst) * 100)}% of this month's ${label} used.`;
  }
  if (!msg) return null;
  return (
    <div className={`plan-banner ${critical ? "critical" : ""}`} role="status">
      <span>{msg}</span><Link to="/settings?tab=billing">View plan & usage</Link>
    </div>
  );
}

function useMetaData() {
  return useApi("/api/meta", { refreshMs: 30000 }).data;
}

function RunDetailRoute() {
  return <RunDetail meta={useMetaData()} />;
}

function ModelsRoute() {
  return <Models meta={useMetaData()} />;
}
