import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useApi } from "../../api";
import { Async, Card, Pager, Tile } from "../../components/ui";
import { fmtAgo, fmtInt, fmtTime, fmtUsd } from "../../format";
import { CallSeverity } from "./common";

const LIMIT = 50;
const SOURCE = { browser: "Web chat", gateway: "App", drift_test: "Drift test", experiment: "Experiment" };

export function Sessions() {
  const [params, setParams] = useSearchParams();
  const nav = useNavigate();
  const offset = Number(params.get("offset") || 0);
  const q = params.get("q") || "";
  const state = useApi(`/api/llm/sessions?limit=${LIMIT}&offset=${offset}${q ? `&q=${encodeURIComponent(q)}` : ""}`, { refreshMs: 10000 });
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Sessions</h1>
          <p>Whole conversations: every call that shares a session id (the X-AOBS-Session header, or the chat for web chats), in order.</p>
        </div>
      </div>
      <div className="filters">
        <label className="field">Search
          <input type="search" placeholder="Session or user id" defaultValue={q}
                 onKeyDown={(e) => e.key === "Enter" && setParams(e.currentTarget.value ? { q: e.currentTarget.value } : {})} />
        </label>
      </div>
      <Card flush>
        <Async state={state}>
          {(d) => d.items.length === 0 ? (
            <div className="empty">No sessions yet. Send <code>X-AOBS-Session</code> with your gateway calls, or chat on a monitored site.</div>
          ) : (
            <>
              <table>
                <thead><tr><th>Last activity</th><th>Conversation</th><th>Source</th><th className="r">Calls</th><th>Issues</th><th className="r">Tokens</th><th className="r">Cost</th></tr></thead>
                <tbody>
                  {d.items.map((s) => (
                    <tr key={s.session_id} className="clickable" onClick={() => nav(`/llm/sessions/${encodeURIComponent(s.session_id)}`)}>
                      <td className="small">{fmtAgo(s.last_at)}<div className="muted">{fmtTime(s.started_at)}</div></td>
                      <td style={{ maxWidth: 420 }}><div className="truncate">{s.preview || "–"}</div>
                        <div className="small muted mono truncate">{s.session_id}{s.end_user ? ` · user ${s.end_user}` : ""}</div></td>
                      <td className="small">{SOURCE[s.source] || s.source}<div className="muted">{s.model}</div></td>
                      <td className="r">{fmtInt(s.calls)}</td>
                      <td>{s.critical ? <span className="badge critical">{s.critical} critical</span> : s.warning ? <span className="badge warning">{s.warning} warning</span> : <span className="badge healthy">✓ None</span>}</td>
                      <td className="r small">{fmtInt(s.tokens)}</td>
                      <td className="r small">{s.source === "browser" ? "–" : fmtUsd(s.cost_usd, 4)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <Pager total={d.total} limit={LIMIT} offset={offset} noun="sessions" onChange={(o) => setParams({ ...(q ? { q } : {}), offset: o })} />
            </>
          )}
        </Async>
      </Card>
    </>
  );
}

export function SessionDetail() {
  const { id } = useParams();
  const state = useApi(`/api/llm/sessions/${encodeURIComponent(id)}`, { refreshMs: 10000 });
  return (
    <Async state={state}>
      {(d) => (
        <>
          <div className="page-head">
            <div>
              <div className="small muted"><Link to="/llm/sessions">Sessions</Link> / <span className="mono">{d.session_id}</span></div>
              <h1 style={{ marginTop: 4 }}>Conversation</h1>
            </div>
          </div>
          <div className="tiles">
            <Tile label="Calls" value={fmtInt(d.totals.calls)} />
            <Tile label="Tokens" value={fmtInt(d.totals.tokens)} />
            <Tile label="Cost" value={fmtUsd(d.totals.cost_usd, 4)} />
            <Tile label="Issues" value={d.totals.critical + d.totals.warning} delta={`${d.totals.critical} critical · ${d.totals.warning} warning`} />
          </div>
          <div className="stack">
            {d.calls.map((c, i) => (
              <Card key={c.id} title={`Turn ${i + 1}`} sub={`${fmtTime(c.created_at)} · ${c.model}`}
                    right={<div className="row"><CallSeverity severity={c.severity} /><Link className="small" to={`/llm/calls/${c.id}`}>Details</Link></div>}>
                {!c.content_stored ? <div className="small muted">Content not stored (workspace privacy settings).</div> : (
                  <>
                    <div className="small muted">User</div>
                    <div className="textblock">{c.last_user || "–"}</div>
                    <div className="small muted" style={{ marginTop: 8 }}>Answer</div>
                    <div className="textblock">{c.response_text || "–"}</div>
                  </>
                )}
                {c.failed_checks.length > 0 && <div className="small" style={{ marginTop: 8 }}>Failed: {c.failed_checks.join(", ")}</div>}
              </Card>
            ))}
          </div>
        </>
      )}
    </Async>
  );
}
