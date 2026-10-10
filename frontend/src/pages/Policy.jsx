import { Bar, BarChart, CartesianGrid, LabelList, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useApi } from "../api";
import Heatmap from "../components/Heatmap";
import { Async, Card, ChartTip, Legend, Tile } from "../components/ui";
import { fmtInt, fmtNum, humanize } from "../format";
import { FAILURE_LABEL, axisProps, usePalette } from "../theme";

export default function Policy() {
  const state = useApi("/api/policy", { refreshMs: 20000 });
  return <Async state={state}>{(d) => <Body d={d} />}</Async>;
}

function Body({ d }) {
  const pal = usePalette();
  const ws = d.warm_start;
  const live = d.live;
  const pol = d.policy;
  const curveColors = {
    "LinUCB policy": pal.series[0],
    "Static playbook": pal.series[1],
    "Always human review": pal.series[2],
    Random: pal.neutral,
    Oracle: pal.muted,
  };
  const curveKeys = ws ? Object.keys(ws.final_avg_reward) : [];
  const actionLabel = Object.fromEntries((pol?.actions || []).map((a) => [a.action, a.label]));
  const rewardData = live.reward_by_action.filter((r) => r.n > 0);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Intervention policy</h1>
          <p>
            A LinUCB contextual bandit decides what to do with a flagged run: continue, inject a reflection prompt, retry the
            step, escalate to a stronger model, ask a human, or terminate. Its context is the detection output (risk, failure-type
            probabilities, novelty, run length, relative spend). Rewards come from reviewed outcomes, and the policy state is
            persisted after every update. Guardrails: runs below the warning threshold always continue, and critical runs are never
            told to continue.
          </p>
        </div>
      </div>

      <div className="tiles">
        <Tile label="Policy updates" value={fmtInt(pol?.n_updates)} delta="offline warm start + live feedback" />
        <Tile label="Live decisions" value={fmtInt(live.decisions)} />
        <Tile label="Decisions with outcome" value={fmtInt(live.rewarded)} />
        <Tile label="Average live reward" value={fmtNum(live.avg_reward)} delta="per reviewed decision" />
        <Tile label="Exploration (α)" value={fmtNum(pol?.alpha, 1)} />
      </div>

      {ws && (
        <div className="grid cols-2" style={{ marginBottom: 16 }}>
          <Card title="Offline warm start" sub={`${fmtInt(ws.rounds)} simulated decisions: cumulative average reward vs baselines`}>
            <ResponsiveContainer width="100%" height={250}>
              <LineChart data={ws.learning_curve} margin={{ top: 4, right: 12, left: -12, bottom: 0 }}>
                <CartesianGrid vertical={false} stroke={pal.grid} />
                <XAxis dataKey="round" {...axisProps(pal)} tickFormatter={(v) => `${v / 1000}k`} />
                <YAxis {...axisProps(pal)} axisLine={false} />
                <ReferenceLine y={0} stroke={pal.axis} />
                <Tooltip content={<ChartTip labelFormatter={(r) => `After ${fmtInt(r)} decisions`} valueFormatter={(v) => v.toFixed(3)} />} />
                {curveKeys.map((k) => <Line key={k} dataKey={k} stroke={curveColors[k]} strokeWidth={2} dot={false} isAnimationActive={false} />)}
              </LineChart>
            </ResponsiveContainer>
            <Legend items={curveKeys.map((k) => ({ label: `${k} (${ws.final_avg_reward[k].toFixed(2)})`, color: curveColors[k], line: true }))} />
            <div className="small muted" style={{ marginTop: 6 }}>
              The oracle knows the true failure and is an upper bound. The policy sees only what the detectors see.
            </div>
          </Card>
          <Card title="What the policy learned" sub="Actions chosen in the last quarter of warm start, by true condition (share of row)">
            <Heatmap rows={ws.action_by_true_label.labels} cols={ws.action_by_true_label.actions} matrix={ws.action_by_true_label.matrix}
                     rowLabel={(l) => FAILURE_LABEL[l]} colLabel={humanize} corner="true condition"
                     format={(v, share) => (v ? `${Math.round(share * 100)}%` : "")} />
          </Card>
        </div>
      )}

      <div className="grid cols-2" style={{ marginBottom: 16 }}>
        <Card title="Live reward by day" sub="Average reward of reviewed decisions">
          {live.daily_reward.length === 0 ? <div className="empty">No reviewed decisions yet.</div> : (
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={live.daily_reward} margin={{ top: 4, right: 12, left: -16, bottom: 0 }}>
                <CartesianGrid vertical={false} stroke={pal.grid} />
                <XAxis dataKey="date" {...axisProps(pal)} tickFormatter={(d) => d.slice(5)} />
                <YAxis {...axisProps(pal)} axisLine={false} />
                <ReferenceLine y={0} stroke={pal.axis} />
                <Tooltip content={<ChartTip valueFormatter={(v, p) => `${v.toFixed(3)} (n=${p.payload.n})`} names={{ avg_reward: "Avg reward" }} />} />
                <Line dataKey="avg_reward" stroke={pal.series[0]} strokeWidth={2} dot={{ r: 4, fill: pal.series[0], stroke: pal.surface, strokeWidth: 2 }} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </Card>
        <Card title="Live reward by action">
          {rewardData.length === 0 ? <div className="empty">No reviewed decisions yet.</div> : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={rewardData} layout="vertical" margin={{ top: 0, right: 44, left: 8, bottom: 0 }}>
                <XAxis type="number" hide domain={[(min) => Math.min(0, min), (max) => Math.max(0, max)]} />
                <YAxis type="category" dataKey="label" width={170} {...axisProps(pal)} axisLine={false} />
                <ReferenceLine x={0} stroke={pal.axis} />
                <Tooltip cursor={{ fill: pal.grid, opacity: 0.4 }} content={<ChartTip valueFormatter={(v, p) => `${v.toFixed(3)} (n=${p.payload.n})`} names={{ avg_reward: "Avg reward" }} />} />
                <Bar dataKey="avg_reward" fill={pal.series[0]} barSize={14} radius={4} isAnimationActive={false}>
                  <LabelList dataKey="avg_reward" position="right" formatter={(v) => v.toFixed(2)} fill={pal.text} fontSize={11} />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </Card>
      </div>

      <div className="grid cols-2">
        <Card title="Live decisions by detected failure">
          {live.action_by_failure.types.length === 0 ? <div className="empty">No decisions yet.</div> : (
            <Heatmap rows={live.action_by_failure.types} cols={live.action_by_failure.actions} matrix={live.action_by_failure.matrix}
                     rowLabel={(l) => FAILURE_LABEL[l] || humanize(l)} colLabel={(a) => humanize(a)} corner="detected" />
          )}
        </Card>
        {ws && (
          <Card title="Simulated outcome model" sub="Assumed P(run succeeds | condition, action) used only for the offline warm start">
            <div className="table-wrap">
              <table>
                <thead><tr><th>Condition</th>{pol.actions.map((a) => <th key={a.action} className="r small" style={{ whiteSpace: "normal" }}>{a.label}</th>)}</tr></thead>
                <tbody>
                  {Object.entries(ws.success_model).map(([cond, row]) => (
                    <tr key={cond}><td className="small">{FAILURE_LABEL[cond]}</td>{pol.actions.map((a) => <td key={a.action} className="r small">{Math.round(row[a.action] * 100)}%</td>)}</tr>
                  ))}
                  <tr><td className="small text-2">Action cost</td>{pol.actions.map((a) => <td key={a.action} className="r small text-2">{a.cost.toFixed(2)}</td>)}</tr>
                </tbody>
              </table>
            </div>
            <div className="small muted" style={{ marginTop: 8 }}>
              Edit <code>ml/simulator.py</code> to match your environment. In production the policy keeps learning from real reviewed outcomes.
            </div>
          </Card>
        )}
      </div>
      <div style={{ marginTop: 16 }}>
        <Card title="Learned weights" sub="Expected-reward coefficient per context feature and action (blue raises, red lowers)">
          {pol && <WeightTable pol={pol} actionLabel={actionLabel} />}
        </Card>
      </div>
    </>
  );
}

function WeightTable({ pol, actionLabel }) {
  const pal = usePalette();
  const feats = pol.context_features;
  const actions = pol.actions.map((a) => a.action);
  const max = Math.max(1e-6, ...actions.flatMap((a) => feats.map((f) => Math.abs(pol.weights[a][f]))));
  const tint = (v) => {
    const alpha = Math.min(1, Math.abs(v) / max) * 0.75;
    const hex = v >= 0 ? pal.div.pos : pal.div.neg;
    const n = parseInt(hex.slice(1), 16);
    return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
  };
  return (
    <div className="table-wrap">
      <table>
        <thead><tr><th>Feature</th>{actions.map((a) => <th key={a} className="r small" style={{ whiteSpace: "normal" }}>{actionLabel[a]}</th>)}</tr></thead>
        <tbody>
          {feats.map((f) => (
            <tr key={f}>
              <td className="small">{humanize(f)}</td>
              {actions.map((a) => {
                const v = pol.weights[a][f];
                return <td key={a} className="r small num" style={{ background: tint(v), border: `2px solid ${pal.surface}` }}>{v.toFixed(2)}</td>;
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
