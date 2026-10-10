import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, useApi } from "../api";
import { Async, Card, ChartTip, FailureTag, Legend, Meter, SeverityBadge, Tile } from "../components/ui";
import { fmtCompact, fmtInt, fmtNum, fmtTime, fmtUsd, humanize } from "../format";
import { FAILURE_LABEL, axisProps, usePalette } from "../theme";

export default function RunDetail({ meta }) {
  const { id } = useParams();
  const state = useApi(`/api/runs/${id}`, { refreshMs: 10000 });
  return <Async state={state}>{(r) => <Body r={r} meta={meta} reload={state.reload} />}</Async>;
}

function Body({ r, meta, reload }) {
  const pal = usePalette();
  const flagStep = r.first_flag_step;
  const traj = r.risk_trajectory.map((risk, i) => ({ step: i + 1, risk }));
  const tokens = r.steps.map((s) => ({ step: s.index + 1, input: s.input_tokens, output: s.output_tokens }));
  const probs = Object.entries(r.probabilities || {}).sort((a, b) => b[1] - a[1]);
  const evidence = new Set(r.signals.flatMap((s) => s.evidence_steps));
  const warn = meta?.thresholds?.warning ?? 0.35;
  const crit = meta?.thresholds?.critical ?? 0.7;

  return (
    <>
      <div className="page-head">
        <div>
          <div className="small muted"><Link to="/runs">Runs</Link> / <span className="mono">{r.id}</span></div>
          <h1 style={{ marginTop: 4 }}>{r.task || "Untitled run"}</h1>
          <p>
            <Link to={`/agents/${r.agent_id}`}>{r.agent?.name || r.agent_id}</Link> · {r.model} · started {fmtTime(r.started_at)} ·{" "}
            {humanize(r.status)}{r.has_final_answer ? " with final answer" : " without a final answer"}
          </p>
        </div>
        <div className="row">
          <SeverityBadge severity={r.severity} />
          <FailureTag type={r.failure_type} />
          {r.open_set_flag && <span className="badge neutral" title="Flagged by rules + unsupervised agreement while the classifier disagreed">Open-set detection</span>}
        </div>
      </div>

      <div className="tiles">
        <Tile label="Risk score" value={fmtNum(r.risk_score)} delta={`model ${r.model_version}`} />
        <Tile label="Steps" value={r.n_steps} delta={r.baseline ? `typical: ${fmtNum(r.baseline.median_steps, 0)}` : undefined} />
        <Tile label="Tokens" value={fmtCompact(r.tokens)} delta={r.baseline ? `typical: ${fmtCompact(r.baseline.median_tokens)}` : undefined} />
        <Tile label="Estimated cost" value={fmtUsd(r.cost_usd, 4)} delta={`${fmtCompact(r.input_tokens)} in · ${fmtCompact(r.output_tokens)} out`} />
        <Tile label="First flagged" value={flagStep == null ? "Never" : `Step ${flagStep + 1}`} delta={flagStep == null ? "" : `of ${r.n_steps}`} />
        <Tile label="Avoidable tokens" value={fmtCompact(r.avoidable_tokens)} delta="spent after first alert" />
      </div>

      <div className="grid cols-2" style={{ marginBottom: 16 }}>
        <Card title="Risk after each step" sub="When the failure became detectable">
          <ResponsiveContainer width="100%" height={210}>
            <LineChart data={traj} margin={{ top: 18, right: 12, left: -18, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke={pal.grid} />
              <XAxis dataKey="step" {...axisProps(pal)} />
              <YAxis domain={[0, 1]} ticks={[0, warn, crit, 1]} {...axisProps(pal)} axisLine={false} />
              <ReferenceLine y={warn} stroke={pal.warning} strokeWidth={1} label={{ value: "warning", position: "insideTopLeft", fill: pal.muted, fontSize: 11 }} />
              <ReferenceLine y={crit} stroke={pal.critical} strokeWidth={1} label={{ value: "critical", position: "insideTopLeft", fill: pal.muted, fontSize: 11 }} />
              {flagStep != null && <ReferenceLine x={flagStep + 1} stroke={pal.text} strokeWidth={1} label={{ value: "first alert", position: "top", fill: pal.text, fontSize: 11 }} />}
              <Tooltip content={<ChartTip labelFormatter={(s) => `Step ${s}`} valueFormatter={(v) => v.toFixed(3)} names={{ risk: "Risk" }} />} />
              <Line dataKey="risk" stroke={pal.series[0]} strokeWidth={2} dot={{ r: 3, fill: pal.series[0], stroke: pal.surface, strokeWidth: 2 }} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </Card>
        <Card title="Tokens per step" sub="Input grows as context accumulates; long loops cost super-linearly">
          <ResponsiveContainer width="100%" height={210}>
            <BarChart data={tokens} margin={{ top: 8, right: 4, left: -6, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke={pal.grid} />
              <XAxis dataKey="step" {...axisProps(pal)} />
              <YAxis {...axisProps(pal)} axisLine={false} tickFormatter={fmtCompact} />
              {flagStep != null && <ReferenceLine x={flagStep + 1} stroke={pal.text} strokeWidth={1} />}
              <Tooltip cursor={{ fill: pal.grid, opacity: 0.4 }} content={<ChartTip labelFormatter={(s) => `Step ${s}`} valueFormatter={fmtInt} names={{ input: "Input", output: "Output" }} />} />
              <Bar dataKey="input" stackId="t" fill={pal.series[0]} stroke={pal.surface} strokeWidth={1} maxBarSize={24} />
              <Bar dataKey="output" stackId="t" fill={pal.series[1]} stroke={pal.surface} strokeWidth={1} maxBarSize={24} radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
          <Legend items={[{ label: "Input tokens", color: pal.series[0] }, { label: "Output tokens", color: pal.series[1] }]} />
        </Card>
      </div>

      <div className="grid cols-3" style={{ marginBottom: 16 }}>
        <Card title="Why it was flagged" sub="Rule detectors with step-level evidence">
          {r.signals.length === 0 ? <div className="muted small">No rule fired. {r.severity !== "healthy" ? "Flagged by the learned models (see class probabilities)." : ""}</div> :
            r.signals.map((s, i) => (
              <div key={i} className={`signal ${s.severity >= 0.7 ? "sev-high" : s.severity >= 0.35 ? "sev-mid" : ""}`}>
                <div className="spread"><FailureTag type={s.failure_type} /><span className="num small">severity {s.severity.toFixed(2)}</span></div>
                <div className="small" style={{ marginTop: 3 }}>{s.message}</div>
                <div className="small muted">Detector: {humanize(s.detector)} · steps {s.evidence_steps.map((x) => x + 1).join(", ")}</div>
              </div>
            ))}
          <h3 style={{ marginTop: 14 }}>Signal sources</h3>
          <dl className="kv">
            <dt>Rule severity</dt><dd className="num">{fmtNum(r.rule_severity)}</dd>
            <dt>Unsupervised novelty</dt><dd className="num">{fmtNum(r.novelty_score)}</dd>
            <dt>Behavior cluster</dt><dd>{r.cluster_id >= 0 ? `Archetype ${r.cluster_id}` : "None (unusual)"}</dd>
          </dl>
        </Card>

        <Card title="Classifier output" sub="Supervised failure-type probabilities">
          {probs.map(([cls, p]) => (
            <div key={cls} style={{ marginBottom: 8 }}>
              <div className="spread small"><span>{FAILURE_LABEL[cls]}</span><span className="num">{(p * 100).toFixed(1)}%</span></div>
              <Meter value={p} color={cls === "healthy" ? pal.good : pal.failure(cls)} />
            </div>
          ))}
        </Card>

        <Card title="Recommended intervention" sub={r.decision?.at_step != null ? `Decided at step ${r.decision.at_step + 1}` : ""}>
          <div style={{ fontSize: 18, fontWeight: 600 }}>{r.decision?.label || humanize(r.recommended_action)}</div>
          <p className="small text-2" style={{ margin: "6px 0 12px" }}>{r.decision?.reason}</p>
          {r.decision?.scores && Object.keys(r.decision.scores).length > 0 && (
            <table>
              <thead><tr><th>Action</th><th className="r">Expected</th><th className="r">Explore</th><th className="r">UCB</th></tr></thead>
              <tbody>
                {Object.entries(r.decision.scores).sort((a, b) => b[1].ucb - a[1].ucb).map(([a, s]) => (
                  <tr key={a} style={a === r.recommended_action ? { fontWeight: 600 } : undefined}>
                    <td className="small">{humanize(a)}</td>
                    <td className="r small">{s.mean.toFixed(2)}</td>
                    <td className="r small">+{s.bonus.toFixed(2)}</td>
                    <td className="r small">{s.ucb.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </div>

      <div className="grid cols-3" style={{ marginBottom: 16 }}>
        <Card title="Steps" className="span-2" flush sub={`${r.steps.length} steps · highlighted rows are evidence for a detector`}>
          <div className="table-wrap">
            <table>
              <thead><tr><th>#</th><th>Action</th><th>Arguments</th><th>Output</th><th className="r">Tokens</th><th className="r">Latency</th></tr></thead>
              <tbody>
                {r.steps.map((s) => (
                  <tr key={s.index} className={s.unregistered || s.status === "error" ? "hl" : evidence.has(s.index) ? "hl-warn" : ""}>
                    <td><span className="pill-step">{s.index + 1}</span></td>
                    <td style={{ whiteSpace: "nowrap" }}>
                      {s.type === "tool_call" ? <code>{s.tool_name}</code> : <span className="text-2">{s.type === "llm" ? "Reasoning" : "Final answer"}</span>}
                      {s.unregistered && <div><span className="badge critical">Not a registered tool</span></div>}
                      {s.status === "error" && !s.unregistered && <div><span className="badge critical">Error</span></div>}
                    </td>
                    <td><code className="truncate" style={{ display: "block", maxWidth: 220 }} title={JSON.stringify(s.arguments)}>{Object.keys(s.arguments || {}).length ? JSON.stringify(s.arguments) : ""}</code></td>
                    <td style={{ maxWidth: 360 }}><pre className="output">{s.output}</pre></td>
                    <td className="r small">{fmtInt(s.input_tokens + s.output_tokens)}</td>
                    <td className="r small">{fmtInt(s.latency_ms)} ms</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
        <div className="stack">
          <FeedbackForm r={r} meta={meta} onSaved={reload} />
          <Card title="Behavioral features">
            <table>
              <tbody>
                {Object.entries(r.features || {}).map(([k, v]) => (
                  <tr key={k}>
                    <td className="small" title={meta?.feature_descriptions?.[k]}>{meta?.feature_descriptions?.[k] || humanize(k)}</td>
                    <td className="r small">{fmtNum(v)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </div>
      </div>
    </>
  );
}

function FeedbackForm({ r, meta, onSaved }) {
  const [label, setLabel] = useState(r.failure_type && r.failure_type !== "novel_anomaly" ? r.failure_type : "healthy");
  const [action, setAction] = useState(r.recommended_action);
  const [resolved, setResolved] = useState(true);
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);

  const submit = async () => {
    setBusy(true);
    setMsg(null);
    try {
      const res = await api(`/api/runs/${r.id}/feedback`, { method: "POST", body: { label, action_taken: action, resolved, notes, reviewer: "dashboard" } });
      setMsg({ ok: true, text: `Saved. Reward ${res.reward.toFixed(2)}${res.policy_updated ? "; policy updated" : ""}${res.retrain_started ? "; retraining started" : ""}.` });
      setNotes("");
      onSaved();
    } catch (e) {
      setMsg({ ok: false, text: e.message });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title="Review this run" sub="Your label trains the classifier; the outcome rewards the policy">
      {r.feedback.length > 0 && (
        <div className="note" style={{ marginBottom: 10 }}>
          {r.feedback.map((f, i) => (
            <div key={i} className="small">
              Labeled <strong>{FAILURE_LABEL[f.label]}</strong> · {humanize(f.action_taken)} · {f.resolved ? "resolved" : "not resolved"} · reward {f.reward}
              {f.notes && <div className="muted">“{f.notes}”</div>}
            </div>
          ))}
        </div>
      )}
      <div className="stack" style={{ gap: 10 }}>
        <label className="field">What actually happened?
          <select value={label} onChange={(e) => setLabel(e.target.value)}>
            {(meta?.classes || ["healthy"]).map((c) => <option key={c} value={c}>{FAILURE_LABEL[c]}</option>)}
          </select>
        </label>
        <label className="field">Intervention applied
          <select value={action} onChange={(e) => setAction(e.target.value)}>
            {(meta?.actions || []).map((a) => <option key={a.id} value={a.id}>{a.label}</option>)}
          </select>
        </label>
        <div className="field">Did the run reach its goal?
          <div className="seg" style={{ alignSelf: "flex-start" }}>
            <button type="button" className={resolved ? "on" : ""} onClick={() => setResolved(true)}>Yes</button>
            <button type="button" className={!resolved ? "on" : ""} onClick={() => setResolved(false)}>No</button>
          </div>
        </div>
        <label className="field">Notes
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Optional" />
        </label>
        <button className="primary" onClick={submit} disabled={busy}>{busy ? "Saving…" : "Submit review"}</button>
        {msg && <div className={msg.ok ? "small" : "error-box small"} style={msg.ok ? { color: "var(--good-text)" } : undefined}>{msg.text}</div>}
      </div>
    </Card>
  );
}
