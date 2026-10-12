import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, useApi } from "../../api";
import { useAuth } from "../../auth";
import { Async, Card, ChartTip } from "../../components/ui";
import { fmtAgo, fmtInt, fmtNum, fmtTime } from "../../format";
import { axisProps, usePalette } from "../../theme";
import { PROVIDER_LABEL } from "./common";

const EMPTY = { name: "", provider: "openai", model: "gpt-4o-mini", credential_id: null, system_prompt: "", prompt: "",
                contract_id: null, similarity_threshold: 0.5, interval_minutes: 360, enabled: true };
const STATUS = { pass: ["healthy", "✓ Pass"], fail: ["critical", "✕ Fail"], error: ["warning", "! Error"], baseline: ["info", "Baseline"], never: ["neutral", "Not run"] };

function StatusBadge({ s }) {
  const [cls, label] = STATUS[s] || STATUS.never;
  return <span className={`badge ${cls}`}>{label}</span>;
}

export default function DriftTests() {
  const [params, setParams] = useSearchParams();
  const tests = useApi("/api/llm/drift-tests", { refreshMs: 30000 });
  const { can } = useAuth();
  const [editing, setEditing] = useState(null);
  const selected = params.get("id");

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Drift tests</h1>
          <p>Providers update models behind the same name. A drift test sends a fixed prompt on a schedule and compares the answer with a
            baseline, so you hear about behavior changes before your users do. Failures raise an alert.</p>
        </div>
        {can("member") && <button className="primary" onClick={() => setEditing(EMPTY)}>New drift test</button>}
      </div>
      {editing && <TestForm initial={editing} onClose={() => setEditing(null)} onSaved={(t) => { setEditing(null); tests.reload(); setParams({ id: t.id }); }} />}
      <Card flush style={{ marginBottom: 16 }}>
        <Async state={tests}>
          {(rows) => rows.length === 0 ? <div className="empty">No drift tests yet.</div> : (
            <table>
              <thead><tr><th>Test</th><th>Model</th><th>Every</th><th>Last run</th><th>Status</th><th className="r">Similarity</th><th></th></tr></thead>
              <tbody>
                {rows.map((t) => (
                  <tr key={t.id} className="clickable" onClick={() => setParams({ id: t.id })} style={String(t.id) === selected ? { fontWeight: 600 } : !t.enabled ? { opacity: 0.55 } : undefined}>
                    <td>{t.name}<div className="small muted truncate">{t.prompt}</div></td>
                    <td className="small">{t.model}<div className="muted">{PROVIDER_LABEL[t.provider]}</div></td>
                    <td className="small">{t.interval_minutes >= 60 ? `${t.interval_minutes / 60} h` : `${t.interval_minutes} min`}</td>
                    <td className="small">{t.last_run_at ? fmtAgo(t.last_run_at) : "Never"}</td>
                    <td><StatusBadge s={t.last_status} /></td>
                    <td className="r small">{t.last_similarity == null ? "–" : fmtNum(t.last_similarity)} <span className="muted">/ {t.similarity_threshold}</span></td>
                    <td className="r" onClick={(e) => e.stopPropagation()} style={{ whiteSpace: "nowrap" }}>
                      {can("member") && <><RunButton id={t.id} onDone={tests.reload} />{" "}<button onClick={() => setEditing(t)}>Edit</button></>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Async>
      </Card>
      {selected && tests.data && <History test={tests.data.find((t) => String(t.id) === selected)} onChange={tests.reload} />}
    </>
  );
}

function RunButton({ id, onDone }) {
  const [busy, setBusy] = useState(false);
  return (
    <button disabled={busy} onClick={async () => {
      setBusy(true);
      try { const r = await api(`/api/llm/drift-tests/${id}/run`, { method: "POST" }); if (r.status === "error") window.alert(r.detail); }
      catch (e) { window.alert(e.message); }
      finally { setBusy(false); onDone(); }
    }}>{busy ? "Running…" : "Run now"}</button>
  );
}

function History({ test, onChange }) {
  const pal = usePalette();
  const runs = useApi(test ? `/api/llm/drift-tests/${test.id}/runs` : null);
  const { can } = useAuth();
  if (!test) return null;
  return (
    <Async state={runs}>
      {(rows) => {
        const series = [...rows].reverse().filter((r) => r.similarity != null).map((r) => ({ t: r.ran_at, similarity: r.similarity }));
        return (
          <div className="grid cols-2">
            <Card title={`${test.name}: similarity to baseline`}>
              {series.length < 2 ? <div className="empty">Run the test a few times to see a trend.</div> : (
                <ResponsiveContainer width="100%" height={220}>
                  <LineChart data={series} margin={{ top: 8, right: 12, left: -16, bottom: 0 }}>
                    <CartesianGrid vertical={false} stroke={pal.grid} />
                    <XAxis dataKey="t" tickFormatter={(t) => fmtTime(t)} {...axisProps(pal)} minTickGap={40} />
                    <YAxis domain={[0, 1]} {...axisProps(pal)} axisLine={false} />
                    <ReferenceLine y={test.similarity_threshold} stroke={pal.critical} label={{ value: "threshold", position: "insideTopLeft", fill: pal.muted, fontSize: 11 }} />
                    <Tooltip content={<ChartTip labelFormatter={(t) => fmtTime(t)} valueFormatter={(v) => v.toFixed(3)} names={{ similarity: "Similarity" }} />} />
                    <Line dataKey="similarity" stroke={pal.series[0]} strokeWidth={2} dot={{ r: 4, fill: pal.series[0], stroke: pal.surface, strokeWidth: 2 }} isAnimationActive={false} />
                  </LineChart>
                </ResponsiveContainer>
              )}
              <h3 style={{ marginTop: 12 }}>Baseline answer</h3>
              <div className="textblock">{test.baseline_text || "Not set yet: the first successful run becomes the baseline."}</div>
            </Card>
            <Card title="Runs" flush>
              {rows.length === 0 ? <div className="empty">No runs yet.</div> : (
                <table>
                  <thead><tr><th>When</th><th>Status</th><th className="r">Similarity</th><th>Detail</th><th></th></tr></thead>
                  <tbody>
                    {rows.slice(0, 25).map((r) => (
                      <tr key={r.id}>
                        <td className="small">{fmtAgo(r.ran_at)}</td><td><StatusBadge s={r.status} /></td>
                        <td className="r small">{r.similarity == null ? "–" : fmtNum(r.similarity)}</td>
                        <td className="small text-2" title={r.response_text}>{r.detail}<div className="muted">{fmtInt(r.latency_ms)} ms · {fmtInt(r.output_tokens)} tokens</div></td>
                        <td className="r">{can("member") && r.response_text && r.status !== "baseline" && (
                          <button onClick={async () => { await api(`/api/llm/drift-tests/${test.id}/baseline/${r.id}`, { method: "POST" }); onChange(); }}>Use as baseline</button>)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Card>
          </div>
        );
      }}
    </Async>
  );
}

function TestForm({ initial, onClose, onSaved }) {
  const creds = useApi("/api/workspace/credentials");
  const contracts = useApi("/api/llm/contracts");
  const [t, setT] = useState(initial);
  const [err, setErr] = useState(null);
  const set = (k, v) => setT({ ...t, [k]: v });
  const save = async () => {
    setErr(null);
    const body = { name: t.name, provider: t.provider, model: t.model, credential_id: t.credential_id ? Number(t.credential_id) : null,
      system_prompt: t.system_prompt, prompt: t.prompt, contract_id: t.contract_id ? Number(t.contract_id) : null,
      similarity_threshold: Number(t.similarity_threshold), interval_minutes: Number(t.interval_minutes), enabled: t.enabled };
    try { onSaved(await api(initial.id ? `/api/llm/drift-tests/${initial.id}` : "/api/llm/drift-tests", { method: initial.id ? "PATCH" : "POST", body })); }
    catch (e) { setErr(e.message); }
  };
  return (
    <Card title={initial.id ? `Edit “${initial.name}”` : "New drift test"} style={{ marginBottom: 16 }}>
      <div className="form-grid">
        <label className="field">Name<input type="text" value={t.name} onChange={(e) => set("name", e.target.value)} /></label>
        <label className="field">Provider
          <select value={t.provider} onChange={(e) => setT({ ...t, provider: e.target.value, credential_id: null })}>
            {Object.entries(PROVIDER_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
        <label className="field">Model<input type="text" value={t.model} onChange={(e) => set("model", e.target.value)} /></label>
        <label className="field">Provider key
          <select value={t.credential_id || ""} onChange={(e) => set("credential_id", e.target.value)}>
            <option value="">Default for provider</option>
            {(creds.data || []).filter((c) => c.provider === t.provider).map((c) => <option key={c.id} value={c.id}>{c.name} ({c.key_hint})</option>)}
          </select>
        </label>
        <label className="field wide">System prompt (optional)<textarea value={t.system_prompt} onChange={(e) => set("system_prompt", e.target.value)} /></label>
        <label className="field wide">Prompt<textarea value={t.prompt} onChange={(e) => set("prompt", e.target.value)} placeholder="A representative request from your app" /></label>
        <label className="field">Also check contract
          <select value={t.contract_id || ""} onChange={(e) => set("contract_id", e.target.value)}>
            <option value="">None</option>{(contracts.data || []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </label>
        <label className="field">Minimum similarity (0–1)<input type="number" step="0.05" min={0} max={1} value={t.similarity_threshold} onChange={(e) => set("similarity_threshold", e.target.value)} /></label>
        <label className="field">Run every (minutes)<input type="number" min={15} value={t.interval_minutes} onChange={(e) => set("interval_minutes", e.target.value)} /></label>
        <label className="check-row"><input type="checkbox" checked={t.enabled} onChange={(e) => set("enabled", e.target.checked)} /> Enabled</label>
      </div>
      <div className="small muted" style={{ marginTop: 8 }}>Runs at temperature 0. Changing the prompt or model resets the baseline. Each run is a real (billed) API call.</div>
      {err && <div className="error-box small" style={{ marginTop: 10 }}>{err}</div>}
      <div className="row" style={{ marginTop: 12 }}>
        <button className="primary" onClick={save} disabled={!t.name || !t.prompt || !t.model}>Save</button>
        <button onClick={onClose}>Cancel</button>
      </div>
    </Card>
  );
}
