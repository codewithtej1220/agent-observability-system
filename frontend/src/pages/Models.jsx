import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Bar, BarChart, CartesianGrid, LabelList, Line, LineChart, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis,
} from "recharts";
import { api, useApi } from "../api";
import Heatmap from "../components/Heatmap";
import PipelineDiagram from "../components/PipelineDiagram";
import { Async, Card, ChartTip, Legend, Tile } from "../components/ui";
import { fmtInt, fmtNum, fmtPct, fmtTime, humanize } from "../format";
import { APPROACH_ORDER, FAILURE_LABEL, FAILURE_ORDER, axisProps, usePalette } from "../theme";

export default function Models({ meta }) {
  const models = useApi("/api/models", { refreshMs: 10000 });
  const [version, setVersion] = useState(null);
  const active = models.data?.versions.find((v) => v.active)?.version;
  const v = version || active;
  const metrics = useApi(v ? `/api/models/${v}/metrics` : null);
  const [msg, setMsg] = useState(null);

  const retrain = async () => {
    const r = await api("/api/models/retrain", { method: "POST" });
    setMsg(r.message);
    models.reload();
  };

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Detection models</h1>
          <p>
            Three learning paradigms work together. Rules give exact, explainable evidence; the unsupervised model flags
            behavior unlike normal traffic without needing labels; the supervised classifier names the failure type and
            catches it within a few steps. Their outputs are fused, and the intervention policy acts on the result.
          </p>
        </div>
        <div className="row">
          {msg && <span className="small text-2">{msg}</span>}
          <button onClick={retrain} disabled={models.data?.retraining}>{models.data?.retraining ? "Retraining…" : "Retrain with new labels"}</button>
        </div>
      </div>

      <Card title="Pipeline" style={{ marginBottom: 16 }}><PipelineDiagram /></Card>

      <Card title="Model versions" flush style={{ marginBottom: 16 }}>
        <Async state={models}>
          {(d) => (
            <div className="table-wrap">
              <table>
                <thead><tr><th>Version</th><th>Created</th><th>Trigger</th><th className="r">Human labels</th><th className="r">Macro F1</th><th className="r">PR-AUC</th><th>Status</th><th></th></tr></thead>
                <tbody>
                  {d.versions.map((m) => (
                    <tr key={m.version} className="clickable" onClick={() => setVersion(m.version)} style={m.version === v ? { fontWeight: 600 } : undefined}>
                      <td>{m.version}</td><td className="small">{fmtTime(m.created_at)}</td><td className="small">{m.trigger}</td>
                      <td className="r">{fmtInt(m.n_human_labels)}</td><td className="r">{fmtNum(m.macro_f1, 3)}</td><td className="r">{fmtNum(m.pr_auc, 3)}</td>
                      <td>{m.active ? <span className="badge healthy">✓ Active</span> : <span className="badge neutral" title={m.notes}>Inactive</span>}</td>
                      <td className="small muted">{m.version === v ? "Showing" : "View"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Async>
      </Card>

      <Async state={metrics}>{(m) => <Metrics m={m} meta={meta} />}</Async>
    </>
  );
}

function Metrics({ m, meta }) {
  const pal = usePalette();
  const nav = useNavigate();
  const b = m.binary;
  const e = m.early_detection;
  const comparison = ["roc_auc", "pr_auc", "recall_at_5pct_fpr"].map((k) => ({
    metric: { roc_auc: "ROC-AUC", pr_auc: "PR-AUC", recall_at_5pct_fpr: "Recall @ 5% FPR" }[k],
    ...Object.fromEntries(m.approach_comparison.map((a) => [a.approach, a[k]])),
  }));
  const robust = m.unseen_failure_robustness || [];
  const heldOut = [...new Set(robust.map((r) => r.held_out))];
  const robustData = heldOut.map((h) => ({
    type: FAILURE_LABEL[h],
    ...Object.fromEntries(robust.filter((r) => r.held_out === h).map((r) => [r.approach, r.recall])),
  }));
  const approachLegend = APPROACH_ORDER.map((a) => ({ label: a, color: pal.approach(a) }));
  const t = m.training || {};
  const map = useApi("/api/behavior-map?limit=900");

  return (
    <>
      <div className="note" style={{ marginBottom: 12 }}>
        Evaluated on {fmtInt(m.test_runs)} held-out runs that were never used for training (model {m.version}). The
        reference data comes from the built-in simulator, which includes deliberately ambiguous healthy behavior
        (pagination, polling, retries). Expect lower numbers on real traffic; the review queue is how the model adapts to it.
      </div>
      <div className="tiles">
        <Tile label="Macro F1 (5 classes)" value={fmtNum(m.macro_f1, 3)} />
        <Tile label="Precision" value={fmtPct(b.precision)} delta={`at risk ≥ ${b.threshold}`} />
        <Tile label="Recall" value={fmtPct(b.recall)} delta={`${b.fn} failures missed`} />
        <Tile label="False positive rate" value={fmtPct(b.false_positive_rate, 2)} delta={`${b.fp} healthy runs flagged`} />
        <Tile label="Caught within 2 steps" value={fmtPct(e.within_2_steps)} delta={`median ${e.median_latency_steps} steps after onset`} />
        <Tile label="Avoidable token share" value={fmtPct(e.avoidable_token_share)} delta="of failing-run tokens after first alert" />
        <Tile label="Healthy runs ever alerted" value={fmtPct(e.healthy_ever_flagged_rate)} delta="at any step, incl. transient" />
      </div>

      <div className="grid cols-2" style={{ marginBottom: 16 }}>
        <Card title="Which paradigm detects what" sub="Each approach alone vs the fused engine, on the same held-out runs">
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={comparison} margin={{ top: 4, right: 8, left: -16, bottom: 0 }} barGap={2}>
              <CartesianGrid vertical={false} stroke={pal.grid} />
              <XAxis dataKey="metric" {...axisProps(pal)} />
              <YAxis domain={[0, 1]} {...axisProps(pal)} axisLine={false} />
              <Tooltip cursor={{ fill: pal.grid, opacity: 0.4 }} content={<ChartTip valueFormatter={(v) => v.toFixed(3)} />} />
              {APPROACH_ORDER.map((a) => <Bar key={a} dataKey={a} fill={pal.approach(a)} maxBarSize={20} radius={[4, 4, 0, 0]} isAnimationActive={false} />)}
            </BarChart>
          </ResponsiveContainer>
          <Legend items={approachLegend} />
        </Card>
        <Card title="Failure types never seen in training" sub="Leave-one-type-out: recall on the held-out type. This is why the paradigms are combined.">
          {robust.length === 0 ? <div className="empty">Run bootstrap without --skip-robustness to compute this study.</div> : (
            <>
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={robustData} margin={{ top: 4, right: 8, left: -16, bottom: 0 }} barGap={2}>
                  <CartesianGrid vertical={false} stroke={pal.grid} />
                  <XAxis dataKey="type" {...axisProps(pal)} />
                  <YAxis domain={[0, 1]} {...axisProps(pal)} axisLine={false} />
                  <Tooltip cursor={{ fill: pal.grid, opacity: 0.4 }} content={({ active, payload, label }) => {
                    if (!active || !payload?.length) return null;
                    const held = heldOut[robustData.findIndex((r) => r.type === label)];
                    return (
                      <div className="chart-tip"><div className="t">Held out: {label}</div>
                        {robust.filter((r) => r.held_out === held).map((r) => (
                          <div key={r.approach} className="r"><span className="tag"><span className="swatch" style={{ background: pal.approach(r.approach) }} />{r.approach}</span>
                            <span className="num">recall {fmtPct(r.recall, 0)} · FPR {fmtPct(r.false_positive_rate, 1)}</span></div>))}
                      </div>
                    );
                  }} />
                  {APPROACH_ORDER.map((a) => <Bar key={a} dataKey={a} fill={pal.approach(a)} maxBarSize={20} radius={[4, 4, 0, 0]} isAnimationActive={false} />)}
                </BarChart>
              </ResponsiveContainer>
              <Legend items={approachLegend} />
              <table style={{ marginTop: 10 }}>
                <thead><tr><th>Recall / false-positive rate</th>{heldOut.map((h) => <th key={h} className="r small">{FAILURE_LABEL[h]}</th>)}</tr></thead>
                <tbody>
                  {APPROACH_ORDER.map((a) => (
                    <tr key={a}>
                      <td className="small"><span className="tag"><span className="swatch" style={{ background: pal.approach(a) }} />{a}</span></td>
                      {heldOut.map((h) => {
                        const r = robust.find((x) => x.held_out === h && x.approach === a);
                        return <td key={h} className="r small num">{r ? `${fmtPct(r.recall, 0)} / ${fmtPct(r.false_positive_rate, 1)}` : "–"}</td>;
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="small muted" style={{ marginTop: 6 }}>
                Rules and unsupervised alone catch unseen failures but flag 10–30% of healthy runs. The fused engine keeps the
                false-positive rate near 1% while recovering much of the recall the supervised model loses.
              </div>
            </>
          )}
        </Card>
      </div>

      <div className="grid cols-3" style={{ marginBottom: 16 }}>
        <Card title="Precision–recall curves">
          <ResponsiveContainer width="100%" height={230}>
            <LineChart margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
              <CartesianGrid stroke={pal.grid} />
              <XAxis type="number" dataKey="x" domain={[0, 1]} {...axisProps(pal)} label={{ value: "Recall", position: "insideBottomRight", offset: -2, fill: pal.muted, fontSize: 11 }} />
              <YAxis type="number" domain={[0, 1]} {...axisProps(pal)} />
              <Tooltip content={<ChartTip labelFormatter={(x) => `Recall ${Number(x).toFixed(2)}`} valueFormatter={(v) => `precision ${v.toFixed(3)}`} />} />
              {APPROACH_ORDER.map((a) => (
                <Line key={a} name={a} data={(m.pr_curves[a] || []).map(([x, y]) => ({ x, y }))} dataKey="y" stroke={pal.approach(a)}
                      strokeWidth={2} dot={false} isAnimationActive={false} />
              ))}
            </LineChart>
          </ResponsiveContainer>
          <Legend items={approachLegend.map((l) => ({ ...l, line: true }))} />
        </Card>
        <Card title="Early detection" sub="Steps between failure onset and first alert">
          <ResponsiveContainer width="100%" height={230}>
            <BarChart data={e.latency_histogram} margin={{ top: 14, right: 8, left: -16, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke={pal.grid} />
              <XAxis dataKey="bucket" {...axisProps(pal)} />
              <YAxis {...axisProps(pal)} axisLine={false} allowDecimals={false} />
              <Tooltip cursor={{ fill: pal.grid, opacity: 0.4 }} content={<ChartTip labelFormatter={(l) => (l === "never" ? "Never detected" : `${l} steps after onset`)} names={{ count: "Failing runs" }} />} />
              <Bar dataKey="count" fill={pal.series[0]} maxBarSize={24} radius={[4, 4, 0, 0]} isAnimationActive={false}>
                <LabelList dataKey="count" position="top" fill={pal.text} fontSize={11} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <table style={{ marginTop: 6 }}>
            <thead><tr><th>Failure</th><th className="r">Detected</th><th className="r">Median delay</th></tr></thead>
            <tbody>{e.by_type.map((r) => <tr key={r.failure_type}><td className="small">{FAILURE_LABEL[r.failure_type]}</td><td className="r small">{fmtPct(r.detected_rate)}</td><td className="r small">{r.median_latency_steps ?? "–"} steps</td></tr>)}</tbody>
          </table>
        </Card>
        <Card title="What the classifier relies on" sub="Permutation importance (drop in macro F1)">
          <ResponsiveContainer width="100%" height={320}>
            <BarChart data={m.feature_importance.slice(0, 10).map((f) => ({ ...f, label: meta?.feature_descriptions?.[f.feature] || humanize(f.feature.replace(/^rule_/, "rule: ")) }))}
                      layout="vertical" margin={{ top: 0, right: 40, left: 4, bottom: 0 }}>
              <XAxis type="number" hide />
              <YAxis type="category" dataKey="feature" width={150} {...axisProps(pal)} axisLine={false} tickFormatter={humanize} />
              <Tooltip cursor={{ fill: pal.grid, opacity: 0.4 }} content={({ active, payload }) => active && payload?.length ? (
                <div className="chart-tip"><strong>{payload[0].payload.label}</strong><div>importance {payload[0].value.toFixed(4)}</div></div>) : null} />
              <Bar dataKey="importance" fill={pal.series[2]} barSize={14} radius={[0, 4, 4, 0]} isAnimationActive={false}>
                <LabelList dataKey="importance" position="right" formatter={(v) => v.toFixed(3)} fill={pal.text} fontSize={11} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </div>

      <div className="grid cols-2" style={{ marginBottom: 16 }}>
        <Card title="Confusion matrix" sub="Rows: true condition · columns: predicted · shading: share of row">
          <Heatmap rows={m.confusion_matrix.labels} cols={m.confusion_matrix.labels} matrix={m.confusion_matrix.matrix}
                   rowLabel={(c) => FAILURE_LABEL[c]} colLabel={(c) => FAILURE_LABEL[c]} corner="true \\ predicted" highlightDiagonal />
          <table style={{ marginTop: 12 }}>
            <thead><tr><th>Class</th><th className="r">Precision</th><th className="r">Recall</th><th className="r">F1</th><th className="r">Support</th></tr></thead>
            <tbody>
              {m.per_class.map((c) => (
                <tr key={c.class}><td className="small">{FAILURE_LABEL[c.class]}</td><td className="r small">{fmtNum(c.precision, 3)}</td>
                  <td className="r small">{fmtNum(c.recall, 3)}</td><td className="r small">{fmtNum(c.f1, 3)}</td><td className="r small">{c.support}</td></tr>
              ))}
            </tbody>
          </table>
        </Card>
        <Card title="Behavior map" sub="Recent runs projected to 2-D (PCA of behavioral features). Click a point to open the run.">
          <Async state={map}>
            {(d) => {
              const groups = [{ key: "healthy", label: "Healthy", color: pal.neutral }, ...FAILURE_ORDER.map((f) => ({ key: f, label: FAILURE_LABEL[f], color: pal.failure(f) }))];
              const byGroup = (k) => d.points.filter((p) => (p.severity === "healthy" ? "healthy" : p.failure_type || "novel_anomaly") === k);
              return (
                <>
                  <ResponsiveContainer width="100%" height={300}>
                    <ScatterChart margin={{ top: 6, right: 8, left: -16, bottom: 0 }}>
                      <CartesianGrid stroke={pal.grid} />
                      <XAxis type="number" dataKey="x" {...axisProps(pal)} tick={false} label={{ value: "component 1", fill: pal.muted, fontSize: 11 }} />
                      <YAxis type="number" dataKey="y" {...axisProps(pal)} tick={false} />
                      <ZAxis range={[28, 28]} />
                      <Tooltip content={({ active, payload }) => active && payload?.length ? (
                        <div className="chart-tip"><strong>{payload[0].payload.agent_id}</strong>
                          <div>{FAILURE_LABEL[payload[0].payload.failure_type] || "Healthy"} · risk {payload[0].payload.risk.toFixed(2)}</div>
                          <div className="muted">archetype {payload[0].payload.cluster >= 0 ? payload[0].payload.cluster : "none"}</div></div>) : null} />
                      {groups.map((g) => {
                        const pts = byGroup(g.key);
                        return pts.length ? <Scatter key={g.key} name={g.label} data={pts} fill={g.color} fillOpacity={g.key === "healthy" ? 0.7 : 0.95}
                                                     stroke={pal.surface} strokeWidth={1} isAnimationActive={false} onClick={(p) => nav(`/runs/${p.id}`)} cursor="pointer" /> : null;
                      })}
                    </ScatterChart>
                  </ResponsiveContainer>
                  <Legend items={groups.filter((g) => byGroup(g.key).length)} />
                  <div className="small muted" style={{ marginTop: 6 }}>
                    HDBSCAN found {d.clusters.length} behavioral archetypes in normal traffic. Runs far from every archetype raise the unsupervised novelty score.
                  </div>
                </>
              );
            }}
          </Async>
        </Card>
      </div>

      <Card title="Training details">
        <dl className="kv">
          <dt>Training runs</dt><dd>{fmtInt(t.train_runs)} simulated + {fmtInt(t.human_labels)} human-labeled</dd>
          <dt>Supervised samples</dt><dd>{fmtInt(t.supervised_samples)} run prefixes (early-detection training)</dd>
          <dt>Unsupervised samples</dt><dd>{fmtInt(t.unsupervised_samples)} prefixes of rule-clean runs (no labels used)</dd>
          <dt>Fusion weights</dt><dd className="mono">{t.fusion_weights ? Object.entries(t.fusion_weights).map(([k, w]) => `${k}=${w}`).join("  ") : "–"}</dd>
          <dt>Open-set gate</dt><dd>{t.open_set_gate ? `novelty ≥ ${t.open_set_gate.novelty} and rule severity ≥ ${t.open_set_gate.rule} (chosen on validation, FPR ≤ 1.5%)` : "disabled"}</dd>
          <dt>Behavior archetypes</dt><dd>{t.n_clusters}</dd>
          {m.human_label_agreement && <><dt>Human label agreement</dt><dd>{fmtPct(m.human_label_agreement.agreement)} of {m.human_label_agreement.labels} labels (in-sample)</dd></>}
          <dt>Training time</dt><dd>{m.training_seconds}s</dd>
        </dl>
      </Card>
    </>
  );
}
