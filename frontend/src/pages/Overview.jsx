import { Link, useNavigate } from "react-router-dom";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useApi } from "../api";
import { useRange } from "../App";
import { Async, Card, ChartTip, FailureTag, Legend, Meter, RiskMeter, SeverityBadge, Tile } from "../components/ui";
import { fmtAgo, fmtCompact, fmtInt, fmtPct, fmtTime, fmtUsd, humanize } from "../format";
import { FAILURE_LABEL, axisProps, usePalette } from "../theme";

function delta(cur, prev, { pct = false, lowerIsBetter = false } = {}) {
  if (prev == null || cur == null) return {};
  const diff = cur - prev;
  if (Math.abs(diff) < 1e-9) return { text: "no change vs previous period" };
  const txt = pct ? `${diff > 0 ? "+" : ""}${(diff * 100).toFixed(1)} pts` : `${diff > 0 ? "+" : ""}${fmtCompact(diff)}`;
  return { text: `${txt} vs previous period`, good: lowerIsBetter ? diff < 0 : diff > 0 };
}

export default function Overview() {
  const { hours } = useRange();
  const state = useApi(`/api/overview?hours=${hours}`, { refreshMs: 15000 });
  return <Async state={state}>{(d) => <OverviewBody d={d} hours={hours} />}</Async>;
}

function OverviewBody({ d, hours }) {
  const pal = usePalette();
  const nav = useNavigate();
  const k = d.kpis;
  const p = d.previous;
  const tickFmt = (t) => fmtTime(t, hours > 24);
  const series = d.timeseries.map((b) => ({ ...b, healthy: b.runs - b.warning - b.critical }));
  const fr = delta(k.flagged_rate, p.flagged_rate, { pct: true, lowerIsBetter: true });
  const runsDelta = delta(k.runs, p.runs);
  const failures = d.failure_breakdown.map((f) => ({ ...f, label: FAILURE_LABEL[f.failure_type] }));
  const actions = d.action_breakdown.filter((a) => a.count > 0);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Overview</h1>
          <p>Agent runs scored in real time for loops, tool thrashing, hallucinated tool calls and token waste. Window: last {hours}h.</p>
        </div>
      </div>

      <div className="tiles">
        <Tile label="Runs" value={fmtInt(k.runs)} delta={runsDelta.text} />
        <Tile label="Flagged rate" value={fmtPct(k.flagged_rate)} delta={fr.text} deltaGood={fr.good}
              hint="Share of runs with risk at warning level or above" />
        <Tile label="Critical runs" value={fmtInt(k.critical)} delta={`${fmtInt(k.flagged)} flagged in total`} />
        <Tile label="Tokens" value={fmtCompact(k.tokens)} delta={`${fmtUsd(k.cost_usd)} estimated cost`} />
        <Tile label="Avoidable spend" value={fmtUsd(k.avoidable_cost_usd)}
              delta={`${fmtCompact(k.avoidable_tokens)} tokens after first alert`}
              hint="Tokens spent by failing runs after the system first flagged them" />
        <Tile label="Median detection step" value={k.median_detection_step == null ? "–" : `Step ${k.median_detection_step + 1}`}
              delta="first alert in flagged runs" />
        <Tile label="Awaiting review" value={fmtInt(d.pending_review)} delta={<Link to="/review">Open review queue</Link>} />
      </div>

      <div className="grid cols-2" style={{ marginBottom: 16 }}>
        <Card title="Runs by severity" sub={`Per ${d.bucket_hours}h bucket`}>
          <ResponsiveContainer width="100%" height={230}>
            <BarChart data={series} margin={{ top: 4, right: 4, left: -12, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke={pal.grid} />
              <XAxis dataKey="t" tickFormatter={tickFmt} {...axisProps(pal)} minTickGap={28} />
              <YAxis {...axisProps(pal)} axisLine={false} allowDecimals={false} />
              <Tooltip cursor={{ fill: pal.grid, opacity: 0.4 }}
                       content={<ChartTip labelFormatter={(t) => fmtTime(t)} names={{ healthy: "Healthy", warning: "Warning", critical: "Critical" }} />} />
              <Bar dataKey="healthy" stackId="s" fill={pal.neutral} stroke={pal.surface} strokeWidth={1} maxBarSize={24} />
              <Bar dataKey="warning" stackId="s" fill={pal.warning} stroke={pal.surface} strokeWidth={1} maxBarSize={24} />
              <Bar dataKey="critical" stackId="s" fill={pal.critical} stroke={pal.surface} strokeWidth={1} maxBarSize={24} radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
          <Legend items={[{ label: "Healthy", color: pal.neutral }, { label: "Warning", color: pal.warning }, { label: "Critical", color: pal.critical }]} />
        </Card>

        <Card title="Token spend" sub="Total tokens vs tokens spent after a run was first flagged">
          <ResponsiveContainer width="100%" height={230}>
            <AreaChart data={series} margin={{ top: 4, right: 4, left: -4, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke={pal.grid} />
              <XAxis dataKey="t" tickFormatter={tickFmt} {...axisProps(pal)} minTickGap={28} />
              <YAxis {...axisProps(pal)} axisLine={false} tickFormatter={fmtCompact} />
              <Tooltip content={<ChartTip labelFormatter={(t) => fmtTime(t)} valueFormatter={fmtCompact}
                                          names={{ tokens: "All tokens", avoidable_tokens: "Avoidable" }} />} />
              <Area dataKey="tokens" stroke={pal.series[0]} fill={pal.series[0]} fillOpacity={0.1} strokeWidth={2} />
              <Area dataKey="avoidable_tokens" stroke={pal.series[1]} fill={pal.series[1]} fillOpacity={0.12} strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
          <Legend items={[{ label: "All tokens", color: pal.series[0], line: true }, { label: "Avoidable (after first alert)", color: pal.series[1], line: true }]} />
        </Card>
      </div>

      <div className="grid cols-3" style={{ marginBottom: 16 }}>
        <Card title="Detected failure types" sub="Flagged runs by predicted failure">
          {failures.every((f) => !f.count) ? <div className="empty">No flagged runs</div> : (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={failures} layout="vertical" margin={{ top: 0, right: 36, left: 8, bottom: 0 }}>
                <XAxis type="number" hide />
                <YAxis type="category" dataKey="label" width={118} {...axisProps(pal)} axisLine={false} />
                <Tooltip cursor={{ fill: pal.grid, opacity: 0.4 }} content={<ChartTip names={{ count: "Runs" }} />} />
                <Bar dataKey="count" barSize={16} radius={[0, 4, 4, 0]} isAnimationActive={false}
                     shape={(props) => <rect x={props.x} y={props.y} width={Math.max(0, props.width)} height={props.height} rx={3}
                                             fill={pal.failure(props.payload.failure_type)} />}>
                  <LabelList dataKey="count" position="right" fill={pal.text} fontSize={12} />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </Card>

        <Card title="Recommended interventions" sub="Policy decisions on flagged runs">
          {actions.length === 0 ? <div className="empty">No interventions</div> : (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={actions} layout="vertical" margin={{ top: 0, right: 36, left: 8, bottom: 0 }}>
                <XAxis type="number" hide />
                <YAxis type="category" dataKey="label" width={170} {...axisProps(pal)} axisLine={false} />
                <Tooltip cursor={{ fill: pal.grid, opacity: 0.4 }} content={<ChartTip names={{ count: "Runs" }} />} />
                <Bar dataKey="count" fill={pal.series[0]} barSize={16} radius={[0, 4, 4, 0]} isAnimationActive={false}>
                  <LabelList dataKey="count" position="right" fill={pal.text} fontSize={12} />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </Card>

        <Card title="Recent alerts" right={<Link className="small" to="/runs?severity=flagged">All flagged</Link>}>
          {d.recent_alerts.length === 0 ? <div className="empty">No alerts</div> : (
            <div className="stack" style={{ gap: 10 }}>
              {d.recent_alerts.slice(0, 6).map((r) => (
                <Link key={r.id} to={`/runs/${r.id}`} style={{ color: "inherit" }}>
                  <div className="spread">
                    <FailureTag type={r.failure_type} />
                    <SeverityBadge severity={r.severity} />
                  </div>
                  <div className="small text-2 truncate">{r.agent_id} · {r.task}</div>
                  <div className="small muted">{fmtAgo(r.started_at)} · {humanize(r.recommended_action)}</div>
                </Link>
              ))}
            </div>
          )}
        </Card>
      </div>

      <Card title="Agents" sub="Sorted by flagged rate" flush right={<Link className="small" to="/agents" style={{ paddingRight: 16 }}>Compare agents</Link>}>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Agent</th><th className="r">Runs</th><th>Flagged rate</th><th className="r">Critical</th>
                <th className="r">Success</th><th className="r">Avg risk</th><th className="r">Tokens</th><th className="r">Avoidable spend</th>
              </tr>
            </thead>
            <tbody>
              {d.agents.map((a) => (
                <tr key={a.agent_id} className="clickable" onClick={() => nav(`/agents/${a.agent_id}`)}>
                  <td><strong>{a.name}</strong><div className="small muted">{a.agent_id}</div></td>
                  <td className="r">{fmtInt(a.runs)}</td>
                  <td>
                    <div className="row" style={{ flexWrap: "nowrap" }}>
                      <Meter value={a.flagged_rate} max={0.5} color={a.flagged_rate > 0.25 ? pal.critical : a.flagged_rate > 0.12 ? pal.warning : pal.series[0]} width={90} />
                      <span className="num small">{fmtPct(a.flagged_rate)}</span>
                    </div>
                  </td>
                  <td className="r">{fmtInt(a.critical)}</td>
                  <td className="r">{fmtPct(a.success_rate)}</td>
                  <td className="r"><RiskMeter risk={a.avg_risk} /></td>
                  <td className="r">{fmtCompact(a.tokens)}</td>
                  <td className="r">{fmtUsd(a.avoidable_cost_usd)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}
