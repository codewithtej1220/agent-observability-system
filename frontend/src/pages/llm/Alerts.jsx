import { useState } from "react";
import { Link } from "react-router-dom";
import { api, useApi } from "../../api";
import { useAuth } from "../../auth";
import { Async, Card, Segmented } from "../../components/ui";
import { fmtAgo, fmtTime } from "../../format";

const EMPTY_RULE = { name: "", metric: "violation_rate", comparison: ">", threshold: 0.1, window_minutes: 60, min_calls: 10,
                     cooldown_minutes: 30, scope: {}, channels: {}, enabled: true };
const PCT_METRICS = new Set(["violation_rate", "error_rate", "avg_adherence"]);

export default function Alerts() {
  const [status, setStatus] = useState("open");
  const events = useApi(`/api/llm/alerts${status === "all" ? "" : `?status=${status}`}`, { refreshMs: 10000 });
  const rules = useApi("/api/llm/alert-rules");
  const metrics = useApi("/api/llm/alert-metrics");
  const { can } = useAuth();
  const [editing, setEditing] = useState(null);

  const setEvent = async (id, s) => { await api(`/api/llm/alerts/${id}`, { method: "PATCH", body: { status: s } }); events.reload(); };

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Alerts</h1>
          <p>Alerts fire on single calls (personal data leaked, prompt injection, a blocked response) or when a metric crosses a threshold over a time window. Window alerts resolve themselves when the condition clears.</p>
        </div>
        {can("member") && <button className="primary" onClick={() => setEditing(EMPTY_RULE)}>New alert rule</button>}
      </div>

      {editing && metrics.data && (
        <RuleForm initial={editing} metrics={metrics.data} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); rules.reload(); }} />
      )}

      <Card flush title="Alerts" right={<div style={{ paddingRight: 16 }}><Segmented value={status} onChange={setStatus}
            options={[{ value: "open", label: "Open" }, { value: "acknowledged", label: "Acknowledged" }, { value: "resolved", label: "Resolved" }, { value: "all", label: "All" }]} /></div>}
            style={{ marginBottom: 16 }}>
        <Async state={events}>
          {(rows) => rows.length === 0 ? <div className="empty">No {status === "all" ? "" : status} alerts.</div> : (
            <table>
              <thead><tr><th>When</th><th>Alert</th><th>Severity</th><th>Delivery</th><th></th></tr></thead>
              <tbody>
                {rows.map((e) => (
                  <tr key={e.id}>
                    <td className="small" style={{ whiteSpace: "nowrap" }}>{fmtAgo(e.created_at)}<div className="muted">{fmtTime(e.created_at)}</div></td>
                    <td><strong className="small">{e.title}</strong><div className="small text-2">{e.message}</div>
                      {e.ref_type === "llm_call" && <Link className="small" to={`/llm/calls/${e.ref_id}`}>Open call</Link>}
                      {e.ref_type === "drift_test" && <Link className="small" to={`/llm/drift?id=${e.ref_id}`}>Open drift test</Link>}</td>
                    <td><span className={`badge ${e.severity === "critical" ? "critical" : e.severity === "warning" ? "warning" : "info"}`}>{e.severity}</span></td>
                    <td className="small">{(e.notified || []).length === 0 ? <span className="muted">in-app</span> :
                      e.notified.map((n, i) => <div key={i}>{n.channel}: {n.ok ? "sent" : <span style={{ color: "var(--critical-text)" }}>{n.error || `HTTP ${n.status}`}</span>}</div>)}</td>
                    <td className="r" style={{ whiteSpace: "nowrap" }}>
                      {can("member") && e.status === "open" && <button onClick={() => setEvent(e.id, "acknowledged")}>Acknowledge</button>}{" "}
                      {can("member") && e.status !== "resolved" && <button onClick={() => setEvent(e.id, "resolved")}>Resolve</button>}
                      {e.status === "resolved" && <span className="small muted">resolved {fmtAgo(e.resolved_at)}</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Async>
      </Card>

      <Card flush title="Alert rules">
        <Async state={rules}>
          {(rows) => rows.length === 0 ? <div className="empty">No alert rules. Drift-test failures still appear above.</div> : (
            <table>
              <thead><tr><th>Rule</th><th>Condition</th><th>Scope</th><th>Channels</th><th>Last fired</th><th></th></tr></thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} style={!r.enabled ? { opacity: 0.55 } : undefined}>
                    <td>{r.name}</td>
                    <td className="small">{r.kind === "event" ? r.metric_label : `${r.metric_label} ${r.comparison} ${PCT_METRICS.has(r.metric) ? `${(r.threshold * 100).toFixed(1)}%` : r.threshold} over ${r.window_minutes} min (≥ ${r.min_calls} calls)`}</td>
                    <td className="small">{Object.entries(r.scope).map(([k, v]) => `${k}: ${v}`).join(", ") || "All calls"}</td>
                    <td className="small">{["in-app", ...Object.keys(r.channels)].join(", ")}</td>
                    <td className="small">{r.last_fired_at ? fmtAgo(r.last_fired_at) : "Never"}</td>
                    <td className="r" style={{ whiteSpace: "nowrap" }}>
                      {can("member") && <>
                        <button onClick={async () => { const t = await api(`/api/llm/alert-rules/${r.id}/test`, { method: "POST" }); window.alert(t.notified.length ? t.notified.map((n) => `${n.channel}: ${n.ok ? "sent" : n.error || n.status}`).join("\n") : "Test alert created (in-app only)."); events.reload(); }}>Test</button>{" "}
                        <button onClick={() => setEditing(r)}>Edit</button>{" "}
                        <button onClick={async () => { if (window.confirm(`Delete "${r.name}"?`)) { await api(`/api/llm/alert-rules/${r.id}`, { method: "DELETE" }); rules.reload(); } }}>Delete</button>
                      </>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Async>
      </Card>
    </>
  );
}

function RuleForm({ initial, metrics, onClose, onSaved }) {
  const contracts = useApi("/api/llm/contracts");
  const [r, setR] = useState({ ...initial, email: (initial.channels?.email || []).join(", "), slack: initial.channels?.slack || "", webhook: initial.channels?.webhook || "" });
  const [err, setErr] = useState(null);
  const isEvent = metrics.event.some((m) => m.id === r.metric);
  const pct = PCT_METRICS.has(r.metric);
  const set = (k, v) => setR({ ...r, [k]: v });
  const save = async () => {
    setErr(null);
    const body = { name: r.name, metric: r.metric, comparison: r.comparison, threshold: Number(r.threshold), window_minutes: Number(r.window_minutes),
      min_calls: Number(r.min_calls), cooldown_minutes: Number(r.cooldown_minutes), enabled: r.enabled, scope: r.scope,
      channels: { slack: r.slack || undefined, webhook: r.webhook || undefined, email: r.email ? r.email.split(",").map((s) => s.trim()).filter(Boolean) : [] } };
    try {
      await api(initial.id ? `/api/llm/alert-rules/${initial.id}` : "/api/llm/alert-rules", { method: initial.id ? "PATCH" : "POST", body });
      onSaved();
    } catch (e) { setErr(e.message); }
  };
  return (
    <Card title={initial.id ? `Edit “${initial.name}”` : "New alert rule"} style={{ marginBottom: 16 }}>
      <div className="form-grid">
        <label className="field">Name<input type="text" value={r.name} onChange={(e) => set("name", e.target.value)} placeholder="e.g. Support bot drifting" /></label>
        <label className="field">Trigger
          <select value={r.metric} onChange={(e) => set("metric", e.target.value)}>
            <optgroup label="On a single call">{metrics.event.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}</optgroup>
            <optgroup label="Over a time window">{metrics.window.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}</optgroup>
          </select>
        </label>
        {!isEvent && (
          <>
            <label className="field">Condition
              <div className="row" style={{ flexWrap: "nowrap" }}>
                <select value={r.comparison} onChange={(e) => set("comparison", e.target.value)} style={{ width: 70 }}>
                  <option value=">">above</option><option value="<">below</option>
                </select>
                <input type="number" step={pct ? "1" : "any"} value={pct ? Math.round(r.threshold * 1000) / 10 : r.threshold}
                       onChange={(e) => set("threshold", pct ? Number(e.target.value) / 100 : e.target.value)} style={{ width: 110 }} />
                {pct && <span className="small">%</span>}
              </div>
            </label>
            <label className="field">Window (minutes)<input type="number" min={5} value={r.window_minutes} onChange={(e) => set("window_minutes", e.target.value)} /></label>
            <label className="field">Minimum calls in window<input type="number" min={1} value={r.min_calls} onChange={(e) => set("min_calls", e.target.value)} /></label>
          </>
        )}
        <label className="field">Cooldown (minutes)<input type="number" min={0} value={r.cooldown_minutes} onChange={(e) => set("cooldown_minutes", e.target.value)} /></label>
        <label className="field">Only for provider
          <select value={r.scope.provider || ""} onChange={(e) => set("scope", { ...r.scope, provider: e.target.value || undefined })}>
            <option value="">Any</option><option value="openai">OpenAI</option><option value="anthropic">Anthropic</option><option value="gemini">Gemini</option>
          </select>
        </label>
        <label className="field">Only for model<input type="text" value={r.scope.model || ""} onChange={(e) => set("scope", { ...r.scope, model: e.target.value || undefined })} placeholder="Any" /></label>
        <label className="field">Only for contract
          <select value={r.scope.contract_id || ""} onChange={(e) => set("scope", { ...r.scope, contract_id: e.target.value ? Number(e.target.value) : undefined })}>
            <option value="">Any</option>{(contracts.data || []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </label>
        <label className="field wide">Slack incoming webhook URL<input type="url" value={r.slack} onChange={(e) => set("slack", e.target.value)} placeholder="https://hooks.slack.com/services/…" /></label>
        <label className="field wide">Generic webhook URL (receives JSON)<input type="url" value={r.webhook} onChange={(e) => set("webhook", e.target.value)} placeholder="https://…" /></label>
        <label className="field wide">Email recipients (comma-separated)
          <input type="text" value={r.email} onChange={(e) => set("email", e.target.value)} disabled={!metrics.email_enabled} />
          {!metrics.email_enabled && <span className="muted">Email needs SMTP settings on the server (AOBS_SMTP_HOST, …).</span>}
        </label>
        <label className="check-row"><input type="checkbox" checked={r.enabled} onChange={(e) => set("enabled", e.target.checked)} /> Enabled</label>
      </div>
      {err && <div className="error-box small" style={{ marginTop: 10 }}>{err}</div>}
      <div className="row" style={{ marginTop: 12 }}>
        <button className="primary" onClick={save} disabled={!r.name}>Save rule</button>
        <button onClick={onClose}>Cancel</button>
      </div>
    </Card>
  );
}
