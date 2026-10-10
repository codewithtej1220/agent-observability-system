import { Link, useParams } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useApi } from "../api";
import { useRange } from "../App";
import ToolFlowGraph from "../components/ToolFlowGraph";
import { Async, Card, ChartTip, FailureTag, Legend, Meter, Tile } from "../components/ui";
import { fmtCompact, fmtInt, fmtNum, fmtPct, fmtTime, fmtUsd } from "../format";
import { axisProps, usePalette } from "../theme";
import { RunTable } from "./Runs";

export default function AgentDetail() {
  const { id } = useParams();
  const { hours } = useRange();
  const state = useApi(`/api/agents/${id}?hours=${hours}`, { refreshMs: 30000 });
  const flagged = useApi(`/api/runs?agent_id=${id}&severity=flagged&limit=8`);
  return <Async state={state}>{(a) => <Body a={a} hours={hours} flagged={flagged.data?.items || []} />}</Async>;
}

function Body({ a, hours, flagged }) {
  const pal = usePalette();
  const s = a.stats;
  const tick = (t) => fmtTime(t, hours > 24);
  const ts = a.timeseries.map((b) => ({ ...b, healthy: b.runs - b.flagged }));
  const registered = new Set(a.registered_tools);

  return (
    <>
      <div className="page-head">
        <div>
          <div className="small muted"><Link to="/agents">Agents</Link> / {a.id}</div>
          <h1 style={{ marginTop: 4 }}>{a.name}</h1>
          <p>{a.description} · {a.model} · {a.framework}</p>
        </div>
        <Link to={`/runs?agent_id=${a.id}`}>All runs for this agent</Link>
      </div>

      <div className="tiles">
        <Tile label="Runs" value={fmtInt(s.runs)} delta={`last ${hours}h`} />
        <Tile label="Flagged rate" value={fmtPct(s.flagged_rate)} delta={`${fmtInt(s.critical)} critical`} />
        <Tile label="Success rate" value={fmtPct(s.success_rate)} delta="healthy runs with a final answer" />
        <Tile label="Avg tokens / run" value={fmtCompact(s.avg_tokens)} delta={a.baseline ? `baseline median ${fmtCompact(a.baseline.median_tokens)}` : undefined} />
        <Tile label="Avg cost / run" value={fmtUsd(s.avg_cost_usd, 3)} delta={`${fmtUsd(s.cost_usd)} total`} />
        <Tile label="p95 run latency" value={`${fmtNum(s.p95_latency_s, 1)} s`} />
        <Tile label="Avoidable spend" value={fmtUsd(s.avoidable_cost_usd)} delta={`${fmtCompact(s.avoidable_tokens)} tokens`} />
      </div>

      <Card title="Tool flow" sub="How runs move between tools. Loops and thrashing show up as heavy red cycles; hallucinated tools as red nodes." style={{ marginBottom: 16 }}>
        <ToolFlowGraph graph={a.tool_graph} />
      </Card>

      <div className="grid cols-2" style={{ marginBottom: 16 }}>
        <Card title="Runs over time">
          <ResponsiveContainer width="100%" height={210}>
            <BarChart data={ts} margin={{ top: 4, right: 4, left: -16, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke={pal.grid} />
              <XAxis dataKey="t" tickFormatter={tick} {...axisProps(pal)} minTickGap={28} />
              <YAxis {...axisProps(pal)} axisLine={false} allowDecimals={false} />
              <Tooltip cursor={{ fill: pal.grid, opacity: 0.4 }} content={<ChartTip labelFormatter={(t) => fmtTime(t)} names={{ healthy: "Healthy", flagged: "Flagged" }} />} />
              <Bar dataKey="healthy" stackId="s" fill={pal.neutral} stroke={pal.surface} strokeWidth={1} maxBarSize={24} />
              <Bar dataKey="flagged" stackId="s" fill={pal.critical} stroke={pal.surface} strokeWidth={1} maxBarSize={24} radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
          <Legend items={[{ label: "Healthy", color: pal.neutral }, { label: "Flagged", color: pal.critical }]} />
        </Card>
        <Card title="Average tokens per run">
          <ResponsiveContainer width="100%" height={210}>
            <LineChart data={ts} margin={{ top: 4, right: 8, left: -4, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke={pal.grid} />
              <XAxis dataKey="t" tickFormatter={tick} {...axisProps(pal)} minTickGap={28} />
              <YAxis {...axisProps(pal)} axisLine={false} tickFormatter={fmtCompact} />
              <Tooltip content={<ChartTip labelFormatter={(t) => fmtTime(t)} valueFormatter={fmtCompact} names={{ avg_tokens: "Avg tokens" }} />} />
              <Line dataKey="avg_tokens" stroke={pal.series[0]} strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </Card>
      </div>

      <div className="grid cols-2">
        <Card title="Tools" flush sub="Registered tools and observed usage">
          <div className="table-wrap">
            <table>
              <thead><tr><th>Tool</th><th className="r">Calls</th><th>Error rate</th><th className="r">Avg latency</th><th className="r">In flagged runs</th></tr></thead>
              <tbody>
                {a.tools.map((t) => (
                  <tr key={t.id} className={t.kind === "unregistered" ? "hl" : ""}>
                    <td><code>{t.id}</code>{t.kind === "unregistered" && <div><span className="badge critical">Not registered</span></div>}</td>
                    <td className="r">{fmtInt(t.calls)}</td>
                    <td><div className="row" style={{ flexWrap: "nowrap" }}><Meter value={t.error_rate} max={0.5} color={t.error_rate > 0.2 ? pal.critical : pal.series[0]} width={60} /><span className="small num">{fmtPct(t.error_rate)}</span></div></td>
                    <td className="r">{t.avg_latency_ms == null ? "–" : `${fmtInt(t.avg_latency_ms)} ms`}</td>
                    <td className="r">{fmtPct(t.flagged_share)}</td>
                  </tr>
                ))}
                {a.registered_tools.filter((t) => !a.tools.some((x) => x.id === t)).map((t) => (
                  <tr key={t}><td><code>{t}</code></td><td className="r muted" colSpan={4}>registered, not used in this window</td></tr>
                ))}
              </tbody>
            </table>
          </div>
          {registered.size === 0 && <div className="note" style={{ margin: 12 }}>No tool registry for this agent; hallucinated tools are inferred from history. Register tools via <code>POST /api/agents</code>.</div>}
        </Card>
        <Card title="Recent flagged runs" flush>
          {flagged.length ? <RunTable rows={flagged} /> : <div className="empty">No flagged runs.</div>}
        </Card>
      </div>
      <div className="small muted" style={{ marginTop: 10 }}>
        Failure mix: {Object.entries(s.failure_mix).filter(([, v]) => v).map(([k, v]) => <span key={k} style={{ marginRight: 12 }}><FailureTag type={k} /> {v}</span>)}
      </div>
    </>
  );
}
