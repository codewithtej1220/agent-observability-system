import { useMemo, useState } from "react";
import { toast } from "sonner";
import { api, useApi } from "../api";
import { Async, Card, Tile } from "../components/ui";
import { fmtAgo, fmtInt } from "../format";

const STATUSES = ["active", "trialing", "past_due", "canceled"];

function UsageCell({ used, limit }) {
  const pct = limit ? used / limit : 0;
  return (
    <span className="num" style={{ color: pct >= 1 ? "var(--critical-text)" : pct >= 0.8 ? "var(--warning-text)" : undefined }}>
      {fmtInt(used)}<span className="muted"> / {limit == null ? "∞" : fmtInt(limit)}</span>
    </span>
  );
}

/** Platform owner console: every workspace's plan and usage. Metadata only, never prompts or responses. */
export default function Admin() {
  const overview = useApi("/api/admin/overview", { refreshMs: 30000 });
  const [q, setQ] = useState("");

  const update = async (ws, body) => {
    try {
      await api(`/api/admin/workspaces/${ws.id}`, { method: "PATCH", body });
      toast.success(`${ws.name}: updated`);
    } catch (e) {
      toast.error(e.message);
    }
  };

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Platform admin</h1>
          <div className="muted small">All workspaces on this server. Shows plan and usage metadata only, never content.</div>
        </div>
      </div>
      <Async state={overview}>
        {(d) => <AdminBody d={d} q={q} setQ={setQ} update={update} />}
      </Async>
    </>
  );
}

function AdminBody({ d, q, setQ, update }) {
  const rows = useMemo(() => {
    const s = q.trim().toLowerCase();
    return s ? d.workspaces.filter((w) => `${w.name} ${w.owner || ""} ${w.plan}`.toLowerCase().includes(s)) : d.workspaces;
  }, [d.workspaces, q]);
  const calls = d.workspaces.reduce((a, w) => a + w.usage.llm_calls, 0);
  const runs = d.workspaces.reduce((a, w) => a + w.usage.agent_runs, 0);
  return (
    <div className="stack" style={{ gap: 16 }}>
      <div className="tiles">
        <Tile label="Workspaces" value={fmtInt(d.workspaces.length)} />
        <Tile label="Users" value={fmtInt(d.users)} />
        <Tile label="Paying MRR" value={`$${fmtInt(d.mrr_usd)}`} hint="Active paid subscriptions × list price" />
        <Tile label={`LLM calls (${d.period})`} value={fmtInt(calls)} />
        <Tile label={`Agent runs (${d.period})`} value={fmtInt(runs)} />
        <Tile label="By plan" value={<span className="small">{Object.entries(d.by_plan).map(([k, v]) => `${k} ${v}`).join(" · ")}</span>} />
      </div>
      <Card title="Workspaces" flush right={
        <input type="search" placeholder="Filter by name, owner or plan" value={q} onChange={(e) => setQ(e.target.value)}
               aria-label="Filter workspaces" style={{ width: 240 }} />
      }>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Workspace</th><th>Owner</th><th className="r">Members</th><th>Plan</th><th>Status</th>
                <th className="r">LLM calls</th><th className="r">Agent runs</th><th>Last call</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((w) => (
                <tr key={w.id}>
                  <td>{w.name}<div className="small muted">#{w.id} · created {fmtAgo(w.created_at)}{w.stripe ? " · Stripe" : ""}</div></td>
                  <td className="small">{w.owner || "–"}</td>
                  <td className="r num">{w.members}</td>
                  <td>
                    <select value={w.subscribed_plan} aria-label={`Plan for ${w.name}`}
                            onChange={(e) => update(w, { plan: e.target.value })}>
                      {d.plans.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                    </select>
                    {w.plan !== w.subscribed_plan && <div className="small muted">effective: {w.plan}</div>}
                  </td>
                  <td>
                    <select value={w.status} aria-label={`Status for ${w.name}`} onChange={(e) => update(w, { plan_status: e.target.value })}>
                      {STATUSES.map((s) => <option key={s} value={s}>{s.replace("_", " ")}</option>)}
                    </select>
                  </td>
                  <td className="r">
                    <UsageCell used={w.usage.llm_calls} limit={w.limits.llm_calls} />
                    {w.usage.llm_calls_unanalyzed > 0 && <div className="small muted">+{fmtInt(w.usage.llm_calls_unanalyzed)} unanalyzed</div>}
                  </td>
                  <td className="r"><UsageCell used={w.usage.agent_runs} limit={w.limits.agent_runs} /></td>
                  <td className="small">{fmtAgo(w.last_call_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
