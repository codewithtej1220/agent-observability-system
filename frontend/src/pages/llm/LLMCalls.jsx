import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useApi } from "../../api";
import { Async, Card, Pager, Tile } from "../../components/ui";
import { fmtAgo, fmtInt, fmtNum, fmtPct, fmtTime, fmtUsd, humanize } from "../../format";
import { CallSeverity, EnforcementBadge, PROVIDER_LABEL } from "./common";

const LIMIT = 50;

export function LLMCalls() {
  const [params, setParams] = useSearchParams();
  const [live, setLive] = useState(true);
  const contracts = useApi("/api/llm/contracts");
  const nav = useNavigate();
  const set = (k, v) => {
    const next = new URLSearchParams(params);
    if (v === "" || v == null) next.delete(k); else next.set(k, v);
    if (k !== "offset") next.delete("offset");
    setParams(next, { replace: true });
  };
  const qs = new URLSearchParams(params);
  qs.set("limit", LIMIT);
  const state = useApi(`/api/llm/calls?${qs.toString()}`, { refreshMs: live ? 4000 : 0 });
  const offset = Number(params.get("offset") || 0);
  const models = state.data?.models || [];

  return (
    <>
      <div className="page-head">
        <div>
          <h1>LLM calls</h1>
          <p>Every request routed through the gateway, newest first, with the result of every check.</p>
        </div>
        <label className="check-row">
          <input type="checkbox" checked={live} onChange={(e) => setLive(e.target.checked)} />
          {live && <span className="live-dot" />} Live
        </label>
      </div>
      <div className="filters">
        <label className="field">Search
          <input type="search" placeholder="Prompt, response or call ID" defaultValue={params.get("q") || ""}
                 onKeyDown={(e) => e.key === "Enter" && set("q", e.currentTarget.value)} onBlur={(e) => set("q", e.currentTarget.value)} />
        </label>
        <label className="field">Model
          <select value={params.get("model") || ""} onChange={(e) => {
            const m = models.find((x) => x.model === e.target.value);
            const next = new URLSearchParams(params);
            if (m) { next.set("model", m.model); next.set("provider", m.provider); } else { next.delete("model"); next.delete("provider"); }
            next.delete("offset");
            setParams(next, { replace: true });
          }}>
            <option value="">All models</option>
            {models.map((m) => <option key={`${m.provider}/${m.model}`} value={m.model}>{PROVIDER_LABEL[m.provider]} · {m.model}</option>)}
          </select>
        </label>
        <label className="field">Result
          <select value={params.get("severity") || ""} onChange={(e) => set("severity", e.target.value)}>
            <option value="">All</option><option value="issues">Issues (warning + critical)</option>
            <option value="critical">Critical</option><option value="warning">Warning</option><option value="ok">Passed</option>
          </select>
        </label>
        <label className="field">Contract
          <select value={params.get("contract_id") || ""} onChange={(e) => set("contract_id", e.target.value)}>
            <option value="">Any</option>
            {(contracts.data || []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </label>
        <label className="field">Enforcement
          <select value={params.get("enforcement") || ""} onChange={(e) => set("enforcement", e.target.value)}>
            <option value="">Any</option><option value="blocked">Blocked</option><option value="repaired">Repaired</option>
            <option value="fallback">Fallback model</option><option value="passed">Checked and passed</option>
          </select>
        </label>
        <label className="field">Source
          <select value={params.get("source") || "apps"} onChange={(e) => set("source", e.target.value)}>
            <option value="apps">Apps and chat sites</option><option value="gateway">Your apps (gateway)</option>
            <option value="browser">Chat sites (extension)</option><option value="drift_test">Drift tests</option><option value="all">All</option>
          </select>
        </label>
      </div>
      <Card flush>
        <Async state={state}>
          {(d) => d.items.length === 0 ? (
            <div className="empty">No calls match. <Link to="/llm/connect">How to connect your LLMs</Link></div>
          ) : (
            <>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr><th>Time</th><th>Model</th><th>Prompt</th><th>Result</th><th>Failed checks</th>
                      <th className="r">Latency</th><th className="r">Tokens</th><th className="r">Cost</th></tr>
                  </thead>
                  <tbody>
                    {d.items.map((c) => (
                      <tr key={c.id} className="clickable" onClick={() => nav(`/llm/calls/${c.id}`)}>
                        <td className="small" style={{ whiteSpace: "nowrap" }}>{fmtAgo(c.created_at)}<div className="muted">{fmtTime(c.created_at)}</div></td>
                        <td className="small"><strong>{c.model}</strong><div className="muted">{c.source === "browser" ? `${PROVIDER_LABEL[c.provider]} web` : PROVIDER_LABEL[c.provider]}{c.contract ? ` · ${c.contract}` : ""}</div></td>
                        <td><div className="truncate small">{c.preview || <span className="muted">(content not stored)</span>}</div></td>
                        <td><div className="row" style={{ gap: 4 }}><CallSeverity severity={c.severity} /><EnforcementBadge action={c.enforcement_action} /></div>
                          {c.status_code >= 400 && c.enforcement_action !== "blocked" && <div className="small muted">HTTP {c.status_code}</div>}</td>
                        <td className="small text-2" style={{ maxWidth: 260 }}>{c.failed_checks.join(" · ") || "–"}</td>
                        <td className="r small">{fmtInt(c.latency_ms)} ms</td>
                        <td className="r small">{fmtInt(c.input_tokens + c.output_tokens)}</td>
                        <td className="r small">{fmtUsd(c.cost_usd, 4)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Pager total={d.total} limit={LIMIT} offset={offset} onChange={(o) => set("offset", o)} />
            </>
          )}
        </Async>
      </Card>
    </>
  );
}

export function LLMCallDetail() {
  const { id } = useParams();
  const state = useApi(`/api/llm/calls/${id}`);
  return <Async state={state}>{(c) => <CallBody c={c} />}</Async>;
}

function CallBody({ c }) {
  const checks = [...c.checks].sort((a, b) => Number(a.passed) - Number(b.passed));
  return (
    <>
      <div className="page-head">
        <div>
          <div className="small muted"><Link to="/llm/calls">LLM calls</Link> / <span className="mono">{c.id}</span></div>
          <h1 style={{ marginTop: 4 }}>{c.model}</h1>
          <p>{PROVIDER_LABEL[c.provider]} · {fmtTime(c.created_at)} · {c.endpoint}{c.contract ? ` · contract ${c.contract}` : ""}
            {c.session_id ? ` · session ${c.session_id}` : ""}{c.end_user ? ` · user ${c.end_user}` : ""}</p>
        </div>
        <div className="row"><EnforcementBadge action={c.enforcement_action} /><CallSeverity severity={c.severity} /></div>
      </div>
      <div className="tiles">
        <Tile label="Status" value={c.status_code} delta={c.finish_reason ? `finish: ${c.finish_reason}` : ""} />
        <Tile label="Latency" value={`${fmtInt(c.latency_ms)} ms`} delta={c.ttft_ms ? `first token ${fmtInt(c.ttft_ms)} ms` : c.streamed ? "streamed" : ""} />
        <Tile label="Tokens" value={fmtInt(c.input_tokens + c.output_tokens)} delta={`${fmtInt(c.input_tokens)} in · ${fmtInt(c.output_tokens)} out${c.usage_estimated ? " (estimated)" : ""}`} />
        <Tile label="Cost" value={fmtUsd(c.cost_usd, 5)} delta={c.judge_cost_usd ? `+ judge ${fmtUsd(c.judge_cost_usd, 5)}` : ""} />
        <Tile label="Adherence" value={c.adherence == null ? "–" : fmtPct(c.adherence)} delta={`${c.violations} rule violations`} />
        <Tile label="Relevance to prompt" value={c.relevance == null ? "–" : fmtNum(c.relevance)} delta="lexical overlap, 0–1" />
      </div>

      <div className="grid cols-2" style={{ marginBottom: 16 }}>
        <div className="stack">
          {!c.content_stored && <div className="note">Prompt and response text were not stored (workspace privacy settings or retention).</div>}
          {c.system_prompt && <Card title="System prompt"><div className="textblock">{c.system_prompt}</div></Card>}
          <Card title="User message" sub={c.n_messages > 1 ? `Last of ${c.n_messages} messages` : ""}>
            <div className="textblock">{c.last_user || "–"}</div>
          </Card>
          <Card title={c.enforcement_action === "blocked" ? "Response (blocked, not returned to the app)" : "Response"}>
            {c.error && c.enforcement_action !== "blocked" ? <div className="error-box small">{c.error}</div> : <div className="textblock">{c.response_text || "–"}</div>}
          </Card>
        </div>
        <div className="stack">
          <Card title="Checks" flush>
            {checks.length === 0 ? <div className="empty">No checks ran.</div> : (
              <table>
                <thead><tr><th>Check</th><th>Result</th><th>Detail</th></tr></thead>
                <tbody>
                  {checks.map((x, i) => (
                    <tr key={i}>
                      <td className="small">{x.label}<div className="muted">{x.source === "judge" ? "LLM judge" : x.source === "builtin" ? "built-in" : "rule"} · {x.severity}</div></td>
                      <td>{x.skipped ? <span className="badge neutral">Skipped</span> : x.passed ? <span className="badge healthy">✓ Pass</span>
                        : <span className={`badge ${x.severity === "critical" ? "critical" : x.severity === "warning" ? "warning" : "neutral"}`}>✕ Fail</span>}</td>
                      <td className="small text-2">{x.detail}{x.score != null && ` (score ${x.score.toFixed(2)})`}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
          {c.attempts?.length > 0 && (
            <Card title="Enforcement attempts" flush>
              <table>
                <thead><tr><th>#</th><th>Model</th><th>Result</th><th>Detail</th></tr></thead>
                <tbody>
                  {c.attempts.map((a, i) => (
                    <tr key={i}><td>{i + 1}</td><td className="small">{a.model}</td><td className="small">{humanize(a.result)}</td>
                      <td className="small text-2">{(a.violations || []).join("; ") || a.detail || (a.status ? `HTTP ${a.status}` : "")}</td></tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}
          {c.tags?.length > 0 && <Card title="Tags"><div className="row">{c.tags.map((t) => <span key={t} className="badge neutral">{t}</span>)}</div></Card>}
        </div>
      </div>
    </>
  );
}
