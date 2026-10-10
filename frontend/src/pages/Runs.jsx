import { useNavigate, useSearchParams } from "react-router-dom";
import { useApi } from "../api";
import { Async, Card, FailureTag, Pager, RiskMeter, SeverityBadge } from "../components/ui";
import { fmtCompact, fmtTime, fmtUsd, humanize, shortId } from "../format";
import { FAILURE_LABEL, FAILURE_ORDER } from "../theme";

const LIMIT = 50;

export default function Runs() {
  const [params, setParams] = useSearchParams();
  const meta = useApi("/api/meta");
  const set = (k, v) => {
    const next = new URLSearchParams(params);
    if (v === "" || v == null) next.delete(k); else next.set(k, v);
    if (k !== "offset") next.delete("offset");
    setParams(next, { replace: true });
  };
  const qs = new URLSearchParams(params);
  qs.set("limit", LIMIT);
  const state = useApi(`/api/runs?${qs.toString()}`, { refreshMs: 20000 });
  const offset = Number(params.get("offset") || 0);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Runs</h1>
          <p>Every agent run with its risk score, detected failure and the intervention the policy recommended.</p>
        </div>
      </div>
      <div className="filters">
        <label className="field">Search
          <input type="search" placeholder="Task or run ID" defaultValue={params.get("q") || ""}
                 onKeyDown={(e) => e.key === "Enter" && set("q", e.currentTarget.value)}
                 onBlur={(e) => set("q", e.currentTarget.value)} />
        </label>
        <label className="field">Agent
          <select value={params.get("agent_id") || ""} onChange={(e) => set("agent_id", e.target.value)}>
            <option value="">All agents</option>
            {meta.data?.agents.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select>
        </label>
        <label className="field">Severity
          <select value={params.get("severity") || ""} onChange={(e) => set("severity", e.target.value)}>
            <option value="">All</option>
            <option value="flagged">Flagged (warning + critical)</option>
            <option value="critical">Critical</option>
            <option value="warning">Warning</option>
            <option value="healthy">Healthy</option>
          </select>
        </label>
        <label className="field">Failure type
          <select value={params.get("failure_type") || ""} onChange={(e) => set("failure_type", e.target.value)}>
            <option value="">Any</option>
            {FAILURE_ORDER.map((f) => <option key={f} value={f}>{FAILURE_LABEL[f]}</option>)}
          </select>
        </label>
        <label className="field">Status
          <select value={params.get("status") || ""} onChange={(e) => set("status", e.target.value)}>
            <option value="">Any</option>
            <option value="running">Running</option>
            <option value="completed">Completed</option>
            <option value="incomplete">Incomplete</option>
          </select>
        </label>
        <label className="field">Sort by
          <select value={params.get("sort") || "recent"} onChange={(e) => set("sort", e.target.value)}>
            <option value="recent">Most recent</option>
            <option value="risk">Highest risk</option>
            <option value="tokens">Most tokens</option>
            <option value="cost">Highest cost</option>
          </select>
        </label>
      </div>
      <Card flush>
        <Async state={state}>
          {(d) => (
            <>
              <RunTable rows={d.items} />
              <Pager total={d.total} limit={LIMIT} offset={offset} onChange={(o) => set("offset", o)} />
            </>
          )}
        </Async>
      </Card>
    </>
  );
}

export function RunTable({ rows, extra }) {
  const nav = useNavigate();
  if (!rows.length) return <div className="empty">No runs match these filters.</div>;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Started</th><th>Agent</th><th>Task</th><th>Severity</th><th>Failure</th><th>Risk</th>
            <th className="r">Steps</th><th className="r">Tokens</th><th className="r">Cost</th><th>Recommended</th>
            {extra && <th>{extra.label}</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className="clickable" onClick={() => nav(`/runs/${r.id}`)}>
              <td className="small" style={{ whiteSpace: "nowrap" }}>{fmtTime(r.started_at)}<div className="muted mono">{shortId(r.id)}</div></td>
              <td className="small">{r.agent_id}</td>
              <td><div className="truncate">{r.task}</div>{r.status === "running" && <span className="badge neutral">Running</span>}</td>
              <td><SeverityBadge severity={r.severity} /></td>
              <td><FailureTag type={r.failure_type} />{r.open_set_flag && <div className="small muted">open-set</div>}</td>
              <td><RiskMeter risk={r.risk_score} /></td>
              <td className="r">{r.n_steps}</td>
              <td className="r">{fmtCompact(r.tokens)}</td>
              <td className="r">{fmtUsd(r.cost_usd, 3)}</td>
              <td className="small">{r.severity === "healthy" ? <span className="muted">–</span> : humanize(r.recommended_action)}</td>
              {extra && <td>{extra.render(r)}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
