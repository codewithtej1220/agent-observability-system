import { Link, useSearchParams } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useApi } from "../api";
import { useRange } from "../App";
import { Async, Card, ChartTip, FailureTag, Legend } from "../components/ui";
import { fmtCompact, fmtInt, fmtNum, fmtPct, fmtTime, fmtUsd } from "../format";
import { FAILURE_LABEL, FAILURE_ORDER, axisProps, usePalette } from "../theme";

const ROWS = [
  ["Runs", (a) => fmtInt(a.runs)],
  ["Flagged rate", (a) => fmtPct(a.flagged_rate)],
  ["Critical runs", (a) => fmtInt(a.critical)],
  ["Success rate", (a) => fmtPct(a.success_rate)],
  ["Average risk", (a) => fmtNum(a.avg_risk)],
  ["Average steps", (a) => fmtNum(a.avg_steps, 1)],
  ["Average tokens", (a) => fmtCompact(a.avg_tokens)],
  ["Average cost", (a) => fmtUsd(a.avg_cost_usd, 3)],
  ["p95 latency", (a) => `${fmtNum(a.p95_latency_s, 1)} s`],
  ["Avoidable spend", (a) => fmtUsd(a.avoidable_cost_usd)],
  ["Median detection step", (a) => (a.median_detection_step == null ? "–" : `Step ${a.median_detection_step + 1}`)],
  ["Top failure", (a) => <FailureTag type={a.top_failure} muted />],
];

export default function Compare() {
  const [params] = useSearchParams();
  const { hours } = useRange();
  const ids = params.get("ids") || "";
  const state = useApi(ids ? `/api/agents/compare?ids=${ids}&hours=${hours}` : null);
  if (!ids) return <div className="empty">Select agents to compare on the <Link to="/agents">Agents</Link> page.</div>;
  return <Async state={state}>{(d) => <Body d={d} hours={hours} />}</Async>;
}

function Body({ d, hours }) {
  const pal = usePalette();
  const ids = d.agents.map((a) => a.id);
  const color = (id) => pal.agent(id, ids);
  const types = FAILURE_ORDER.filter((t) => t !== "novel_anomaly");
  const mix = types.map((t) => ({ type: FAILURE_LABEL[t], ...Object.fromEntries(d.agents.map((a) => [a.id, a.failure_mix[t]])) }));
  const names = Object.fromEntries(d.agents.map((a) => [a.id, a.name]));

  return (
    <>
      <div className="page-head">
        <div>
          <div className="small muted"><Link to="/agents">Agents</Link> / Compare</div>
          <h1 style={{ marginTop: 4 }}>Agent comparison</h1>
          <p>{d.agents.map((a) => a.name).join(" vs ")} · last {hours}h</p>
        </div>
      </div>

      <Card flush style={{ marginBottom: 16 }}>
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Metric</th>{d.agents.map((a) => (
                <th key={a.id} className="r"><span className="tag" style={{ justifyContent: "flex-end" }}><span className="swatch" style={{ background: color(a.id) }} /><Link to={`/agents/${a.id}`}>{a.name}</Link></span></th>
              ))}</tr>
            </thead>
            <tbody>
              {ROWS.map(([label, fn]) => (
                <tr key={label}><td className="text-2">{label}</td>{d.agents.map((a) => <td key={a.id} className="r">{fn(a)}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="grid cols-2">
        <Card title="Flagged rate over time">
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={d.flag_rate_series} margin={{ top: 4, right: 8, left: -10, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke={pal.grid} />
              <XAxis dataKey="t" tickFormatter={(t) => fmtTime(t, true)} {...axisProps(pal)} minTickGap={36} />
              <YAxis tickFormatter={(v) => fmtPct(v, 0)} {...axisProps(pal)} axisLine={false} />
              <Tooltip content={<ChartTip labelFormatter={(t) => fmtTime(t)} valueFormatter={(v) => fmtPct(v)} names={names} />} />
              {ids.map((id) => <Line key={id} dataKey={id} stroke={color(id)} strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />)}
            </LineChart>
          </ResponsiveContainer>
          <Legend items={d.agents.map((a) => ({ label: a.name, color: color(a.id), line: true }))} />
        </Card>
        <Card title="Flagged runs by failure type">
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={mix} margin={{ top: 4, right: 8, left: -16, bottom: 0 }} barGap={2}>
              <CartesianGrid vertical={false} stroke={pal.grid} />
              <XAxis dataKey="type" {...axisProps(pal)} />
              <YAxis {...axisProps(pal)} axisLine={false} allowDecimals={false} />
              <Tooltip cursor={{ fill: pal.grid, opacity: 0.4 }} content={<ChartTip names={names} />} />
              {ids.map((id) => <Bar key={id} dataKey={id} fill={color(id)} maxBarSize={20} radius={[4, 4, 0, 0]} isAnimationActive={false} />)}
            </BarChart>
          </ResponsiveContainer>
          <Legend items={d.agents.map((a) => ({ label: a.name, color: color(a.id) }))} />
        </Card>
      </div>
    </>
  );
}
