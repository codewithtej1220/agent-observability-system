import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bar, BarChart, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useApi } from "../api";
import { useRange } from "../App";
import { Async, Card, ChartTip, FailureTag, Legend } from "../components/ui";
import { fmtCompact, fmtInt, fmtNum, fmtPct, fmtUsd } from "../format";
import { FAILURE_LABEL, FAILURE_ORDER, axisProps, usePalette } from "../theme";

export default function Agents() {
  const { hours } = useRange();
  const state = useApi(`/api/agents?hours=${hours}`, { refreshMs: 30000 });
  return <Async state={state}>{(agents) => <Body agents={agents} hours={hours} />}</Async>;
}

function Body({ agents, hours }) {
  const pal = usePalette();
  const nav = useNavigate();
  const [selected, setSelected] = useState([]);
  const toggle = (id) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : s.length >= 4 ? s : [...s, id]));
  const active = agents.filter((a) => a.runs > 0);
  const byFlag = [...active].sort((a, b) => b.flagged_rate - a.flagged_rate);
  const mix = active.map((a) => ({ name: a.name, ...a.failure_mix }));
  const types = FAILURE_ORDER.filter((t) => t !== "novel_anomaly");
  const perSuccess = active
    .map((a) => ({ name: a.name, cost_per_success: a.cost_usd / Math.max(1, Math.round(a.runs * a.success_rate)) }))
    .sort((x, y) => y.cost_per_success - x.cost_per_success);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Agents</h1>
          <p>Reliability, cost and failure profile of each monitored agent over the last {hours}h. Select up to four agents to compare them side by side.</p>
        </div>
        <button className="primary" disabled={selected.length < 2} onClick={() => nav(`/compare?ids=${selected.join(",")}`)}>
          Compare {selected.length ? `(${selected.length})` : ""}
        </button>
      </div>

      <Card flush style={{ marginBottom: 16 }}>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th></th><th>Agent</th><th>Model / framework</th><th className="r">Runs</th><th className="r">Flagged</th>
                <th className="r">Success</th><th>Top failure</th><th className="r">Avg steps</th><th className="r">Avg tokens</th>
                <th className="r">Avg cost</th><th className="r">p95 latency</th><th className="r">Avoidable spend</th>
              </tr>
            </thead>
            <tbody>
              {agents.map((a) => (
                <tr key={a.id} className="clickable" onClick={() => nav(`/agents/${a.id}`)}>
                  <td onClick={(e) => e.stopPropagation()}>
                    <input type="checkbox" aria-label={`Select ${a.name}`} checked={selected.includes(a.id)} onChange={() => toggle(a.id)} />
                  </td>
                  <td><strong>{a.name}</strong><div className="small muted">{a.description}</div></td>
                  <td className="small">{a.model}<div className="muted">{a.framework}</div></td>
                  <td className="r">{fmtInt(a.runs)}</td>
                  <td className="r">{fmtPct(a.flagged_rate)}</td>
                  <td className="r">{fmtPct(a.success_rate)}</td>
                  <td><FailureTag type={a.top_failure} /></td>
                  <td className="r">{fmtNum(a.avg_steps, 1)}</td>
                  <td className="r">{fmtCompact(a.avg_tokens)}</td>
                  <td className="r">{fmtUsd(a.avg_cost_usd, 3)}</td>
                  <td className="r">{fmtNum(a.p95_latency_s, 1)} s</td>
                  <td className="r">{fmtUsd(a.avoidable_cost_usd)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="grid cols-3" style={{ marginTop: 16 }}>
        <Card title="Flagged rate" sub="Share of runs at warning or critical">
          <ResponsiveContainer width="100%" height={230}>
            <BarChart data={byFlag} layout="vertical" margin={{ top: 0, right: 44, left: 8, bottom: 0 }}>
              <XAxis type="number" hide domain={[0, "dataMax"]} />
              <YAxis type="category" dataKey="name" width={130} {...axisProps(pal)} axisLine={false} />
              <Tooltip cursor={{ fill: pal.grid, opacity: 0.4 }} content={<ChartTip valueFormatter={(v) => fmtPct(v)} names={{ flagged_rate: "Flagged rate" }} />} />
              <Bar dataKey="flagged_rate" fill={pal.series[0]} barSize={16} radius={[0, 4, 4, 0]} isAnimationActive={false}>
                <LabelList dataKey="flagged_rate" position="right" formatter={(v) => fmtPct(v)} fill={pal.text} fontSize={12} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Card>

        <Card title="Failure mix" sub="Flagged runs by predicted failure type">
          <ResponsiveContainer width="100%" height={230}>
            <BarChart data={mix} layout="vertical" margin={{ top: 0, right: 8, left: 8, bottom: 0 }}>
              <XAxis type="number" hide />
              <YAxis type="category" dataKey="name" width={130} {...axisProps(pal)} axisLine={false} />
              <Tooltip cursor={{ fill: pal.grid, opacity: 0.4 }} content={<ChartTip names={FAILURE_LABEL} />} />
              {types.map((t, i) => (
                <Bar key={t} dataKey={t} stackId="m" fill={pal.failure(t)} stroke={pal.surface} strokeWidth={2} barSize={16}
                     radius={i === types.length - 1 ? [0, 4, 4, 0] : 0} isAnimationActive={false} />
              ))}
            </BarChart>
          </ResponsiveContainer>
          <Legend items={types.map((t) => ({ label: FAILURE_LABEL[t], color: pal.failure(t) }))} />
        </Card>

        <Card title="Cost per successful run" sub="Total estimated cost divided by healthy runs that reached an answer">
          <ResponsiveContainer width="100%" height={230}>
            <BarChart data={perSuccess} layout="vertical" margin={{ top: 0, right: 56, left: 8, bottom: 0 }}>
              <XAxis type="number" hide />
              <YAxis type="category" dataKey="name" width={130} {...axisProps(pal)} axisLine={false} />
              <Tooltip cursor={{ fill: pal.grid, opacity: 0.4 }} content={<ChartTip valueFormatter={(v) => fmtUsd(v, 4)} names={{ cost_per_success: "Cost per success" }} />} />
              <Bar dataKey="cost_per_success" fill={pal.series[0]} barSize={16} radius={[0, 4, 4, 0]} isAnimationActive={false}>
                <LabelList dataKey="cost_per_success" position="right" formatter={(v) => fmtUsd(v, 3)} fill={pal.text} fontSize={12} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </div>
    </>
  );
}
