import { Link, useNavigate } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useApi } from "../../api";
import { useRange } from "../../App";
import { Async, Card, ChartTip, Legend, Meter, Tile } from "../../components/ui";
import { fmtAgo, fmtCompact, fmtInt, fmtPct, fmtTime, fmtUsd } from "../../format";
import { axisProps, usePalette } from "../../theme";
import { CallSeverity, EnforcementBadge, PROVIDER_LABEL } from "./common";

export default function LLMOverview() {
  const { hours } = useRange();
  const state = useApi(`/api/llm/overview?hours=${hours}`, { refreshMs: 15000 });
  return <Async state={state}>{(d) => <Body d={d} hours={hours} />}</Async>;
}

function deltaPct(cur, prev, lowerIsBetter = true) {
  if (cur == null || prev == null) return {};
  const diff = cur - prev;
  if (Math.abs(diff) < 1e-9) return { text: "no change vs previous period" };
  return { text: `${diff > 0 ? "+" : ""}${(diff * 100).toFixed(1)} pts vs previous period`, good: lowerIsBetter ? diff < 0 : diff > 0 };
}

function Body({ d, hours }) {
  const pal = usePalette();
  const nav = useNavigate();
  const k = d.kpis;
  if (k.calls === 0) {
    return (
      <>
        <div className="page-head"><div><h1>LLM overview</h1></div></div>
        <Card>
          <div className="empty">
            <div style={{ fontSize: 15, color: "var(--text)", marginBottom: 6 }}>No LLM calls in the last {hours}h.</div>
            Route your OpenAI, Claude or Gemini calls through the gateway to start monitoring.{" "}
            <Link to="/llm/connect">Connect your LLMs</Link>
          </div>
        </Card>
      </>
    );
  }
  const viol = deltaPct(k.violation_rate, d.previous.violation_rate);
  const err = deltaPct(k.error_rate, d.previous.error_rate);
  const tick = (t) => fmtTime(t, hours > 24);
  const series = d.timeseries.map((b) => ({ ...b, ok: b.calls - b.violations - b.errors }));
  const models = d.by_model.map((m) => ({ ...m, label: `${m.model}`, adherence_pct: m.adherence }));

  return (
    <>
      <div className="page-head">
        <div>
          <h1>LLM overview</h1>
          <p>How your models are behaving across every app routed through the gateway: instruction adherence, failures, latency and spend. Last {hours}h.</p>
        </div>
      </div>
      <div className="tiles">
        <Tile label="LLM calls" value={fmtInt(k.calls)} delta={`${fmtInt(d.previous.calls)} in previous period`} />
        <Tile label="Rule violation rate" value={fmtPct(k.violation_rate)} delta={viol.text} deltaGood={viol.good} hint="Share of calls that broke at least one contract rule" />
        <Tile label="Average adherence" value={k.adherence == null ? "–" : fmtPct(k.adherence)} delta="share of rules passed" />
        <Tile label="Error rate" value={fmtPct(k.error_rate)} delta={err.text} deltaGood={err.good} />
        <Tile label="p95 latency" value={k.p95_latency_ms == null ? "–" : `${fmtInt(k.p95_latency_ms)} ms`} delta={k.avg_ttft_ms ? `first token ${fmtInt(k.avg_ttft_ms)} ms` : ""} />
        <Tile label="Spend" value={fmtUsd(k.cost_usd)} delta={`${fmtCompact(k.input_tokens + k.output_tokens)} tokens · judge ${fmtUsd(k.judge_cost_usd)}`} />
        <Tile label="Blocked / repaired" value={`${fmtInt(k.blocked)} / ${fmtInt(k.repaired)}`} delta="by enforcement" />
        <Tile label="Open alerts" value={fmtInt(k.open_alerts)} delta={<Link to="/llm/alerts">View alerts</Link>} />
      </div>

      <div className="grid cols-2" style={{ marginBottom: 16 }}>
        <Card title="Calls by outcome" sub={`Per ${d.bucket_hours}h bucket`}>
          <ResponsiveContainer width="100%" height={230}>
            <BarChart data={series} margin={{ top: 4, right: 4, left: -12, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke={pal.grid} />
              <XAxis dataKey="t" tickFormatter={tick} {...axisProps(pal)} minTickGap={28} />
              <YAxis {...axisProps(pal)} axisLine={false} allowDecimals={false} />
              <Tooltip cursor={{ fill: pal.grid, opacity: 0.4 }} content={<ChartTip labelFormatter={(t) => fmtTime(t)} names={{ ok: "Passed", violations: "Rule violations", errors: "Errors" }} />} />
              <Bar dataKey="ok" stackId="s" fill={pal.neutral} stroke={pal.surface} strokeWidth={1} maxBarSize={24} />
              <Bar dataKey="violations" stackId="s" fill={pal.warning} stroke={pal.surface} strokeWidth={1} maxBarSize={24} />
              <Bar dataKey="errors" stackId="s" fill={pal.critical} stroke={pal.surface} strokeWidth={1} maxBarSize={24} radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
          <Legend items={[{ label: "Passed", color: pal.neutral }, { label: "Rule violations", color: pal.warning }, { label: "Errors", color: pal.critical }]} />
        </Card>
        <Card title="Most-violated checks">
          {d.top_failed_checks.length === 0 ? <div className="empty">No failed checks. Add rules in a <Link to="/llm/contracts">contract</Link>.</div> : (
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={d.top_failed_checks.slice(0, 8)} layout="vertical" margin={{ top: 0, right: 40, left: 8, bottom: 0 }}>
                <XAxis type="number" hide />
                <YAxis type="category" dataKey="label" width={190} {...axisProps(pal)} axisLine={false} />
                <Tooltip cursor={{ fill: pal.grid, opacity: 0.4 }} content={<ChartTip names={{ count: "Calls" }} />} />
                <Bar dataKey="count" fill={pal.series[1]} barSize={14} radius={[0, 4, 4, 0]} isAnimationActive={false}>
                  <LabelList dataKey="count" position="right" fill={pal.text} fontSize={12} />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </Card>
      </div>

      <Card title="Adherence by model" sub="Compare how well each model follows your rules" flush style={{ marginBottom: 16 }}>
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Model</th><th className="r">Calls</th><th>Adherence</th><th className="r">Violation rate</th><th className="r">Judge score</th>
                <th className="r">Errors</th><th className="r">p50 / p95 latency</th><th className="r">Cost</th></tr>
            </thead>
            <tbody>
              {models.map((m) => (
                <tr key={`${m.provider}/${m.model}`} className="clickable" onClick={() => nav(`/llm/calls?provider=${m.provider}&model=${encodeURIComponent(m.model)}`)}>
                  <td><strong>{m.model}</strong><div className="small muted">{PROVIDER_LABEL[m.provider]}</div></td>
                  <td className="r">{fmtInt(m.calls)}</td>
                  <td>{m.adherence == null ? <span className="muted small">no rules</span> : (
                    <div className="row" style={{ flexWrap: "nowrap" }}>
                      <Meter value={m.adherence} color={m.adherence < 0.8 ? pal.critical : m.adherence < 0.95 ? pal.warning : pal.good} width={90} />
                      <span className="num small">{fmtPct(m.adherence)}</span>
                    </div>)}</td>
                  <td className="r">{fmtPct(m.violation_rate)}</td>
                  <td className="r">{m.judge_score == null ? "–" : m.judge_score.toFixed(2)}</td>
                  <td className="r">{fmtPct(m.error_rate)}</td>
                  <td className="r">{fmtInt(m.p50_latency_ms)} / {fmtInt(m.p95_latency_ms)} ms</td>
                  <td className="r">{fmtUsd(m.cost_usd, 3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="grid cols-2">
        <Card title="By contract" flush>
          <table>
            <thead><tr><th>Contract</th><th>Mode</th><th className="r">Calls</th><th className="r">Adherence</th><th className="r">Blocked</th><th className="r">Repaired</th></tr></thead>
            <tbody>
              {d.by_contract.map((c) => (
                <tr key={c.contract_id ?? "none"} className={c.contract_id ? "clickable" : ""} onClick={() => c.contract_id && nav(`/llm/contracts?id=${c.contract_id}`)}>
                  <td>{c.name}</td><td className="small">{c.mode || "–"}</td><td className="r">{fmtInt(c.calls)}</td>
                  <td className="r">{c.adherence == null ? "–" : fmtPct(c.adherence)}</td><td className="r">{fmtInt(c.blocked)}</td><td className="r">{fmtInt(c.repaired)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
        <Card title="Recent issues" right={<Link className="small" to="/llm/calls?severity=issues">All issues</Link>}>
          {d.recent_issues.length === 0 ? <div className="empty">No issues.</div> : (
            <div className="stack" style={{ gap: 10 }}>
              {d.recent_issues.map((c) => (
                <Link key={c.id} to={`/llm/calls/${c.id}`} style={{ color: "inherit" }}>
                  <div className="spread"><span className="small"><strong>{c.model}</strong> · {fmtAgo(c.created_at)}</span>
                    <span className="row" style={{ gap: 6 }}><EnforcementBadge action={c.enforcement_action} /><CallSeverity severity={c.severity} /></span></div>
                  <div className="small text-2 truncate">{c.failed_checks.join(" · ") || c.preview}</div>
                </Link>
              ))}
            </div>
          )}
        </Card>
      </div>
    </>
  );
}
