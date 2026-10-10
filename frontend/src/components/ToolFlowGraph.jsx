import { useMemo, useState } from "react";
import { fmtInt, fmtPct } from "../format";
import { usePalette } from "../theme";

const W = 146;
const H = 48;
const COL_GAP = 190;
const ROW_GAP = 66;
const PAD = 24;

/** Layered layout: columns by typical step position, rows by call volume. */
function layout(nodes, edges, minShare) {
  const runs = nodes.find((n) => n.id === "START")?.calls || 1;
  const keep = new Set(nodes.filter((n) => n.kind === "terminal" || n.calls >= minShare * runs).map((n) => n.id));
  const inner = nodes.filter((n) => keep.has(n.id) && n.kind !== "terminal");
  const pos = inner.map((n) => n.avg_position);
  const lo = Math.min(...pos, 1);
  const hi = Math.max(...pos, 1);
  const k = Math.max(1, Math.min(5, inner.length));
  const colOf = (p) => 1 + (hi - lo < 1e-6 ? 0 : Math.round(((p - lo) / (hi - lo)) * (k - 1)));
  const cols = {};
  inner.forEach((n) => { (cols[colOf(n.avg_position)] ||= []).push(n); });
  const last = k + 1;
  cols[0] = nodes.filter((n) => n.id === "START");
  cols[last] = nodes.filter((n) => keep.has(n.id) && (n.id === "END" || n.id === "INCOMPLETE"));
  const maxRows = Math.max(...Object.values(cols).map((c) => c.length));
  const height = PAD * 2 + maxRows * ROW_GAP;
  const placed = {};
  Object.entries(cols).forEach(([c, list]) => {
    list.sort((a, b) => b.calls - a.calls);
    const offset = (height - list.length * ROW_GAP) / 2;
    list.forEach((n, i) => { placed[n.id] = { ...n, col: Number(c), x: PAD + Number(c) * COL_GAP, y: offset + i * ROW_GAP + (ROW_GAP - H) / 2 }; });
  });
  const shown = edges.filter((e) => placed[e.source] && placed[e.target] && e.count >= Math.max(1, minShare * runs * 0.5));
  return { placed, edges: shown, width: PAD * 2 + last * COL_GAP + W, height: height + 30, runs };
}

function edgePath(s, t) {
  if (s.id === t.id) {
    const x = s.x + W - 18;
    const y = s.y;
    return `M ${x} ${y} C ${x - 4} ${y - 34}, ${x + 34} ${y - 30}, ${x + 18} ${y + 6}`;
  }
  if (t.col > s.col) {
    const x1 = s.x + W, y1 = s.y + H / 2, x2 = t.x - 6, y2 = t.y + H / 2;
    const dx = (x2 - x1) * 0.5;
    return `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`;
  }
  // Backward or same-column edge: route as an arc below the nodes.
  const x1 = s.x + W / 2, y1 = s.y + H, x2 = t.x + W / 2 + 8, y2 = t.y + H + 6;
  const drop = 30 + Math.abs(x1 - x2) * 0.12;
  return `M ${x1} ${y1} C ${x1} ${y1 + drop}, ${x2} ${y2 + drop}, ${x2} ${y2}`;
}

export default function ToolFlowGraph({ graph }) {
  const pal = usePalette();
  const [minShare, setMinShare] = useState(0.02);
  const [hover, setHover] = useState(null);
  const g = useMemo(() => layout(graph.nodes, graph.edges, minShare), [graph, minShare]);
  if (!graph.nodes.length) return <div className="empty">No runs in this window.</div>;
  const maxCount = Math.max(...g.edges.map((e) => e.count), 1);
  const related = (e) => !hover || e.source === hover || e.target === hover;

  return (
    <div>
      <div className="spread small" style={{ marginBottom: 6 }}>
        <span className="muted">Built from {fmtInt(graph.runs)} recent runs. Hover a node to isolate its transitions.</span>
        <label className="row">Hide rare paths
          <select value={minShare} onChange={(e) => setMinShare(Number(e.target.value))}>
            <option value={0}>Show all</option>
            <option value={0.02}>&lt; 2% of runs</option>
            <option value={0.05}>&lt; 5% of runs</option>
          </select>
        </label>
      </div>
      <div className="table-wrap">
        <svg viewBox={`0 0 ${g.width} ${g.height}`} width="100%" role="img" aria-label="Tool transition graph"
             style={{ display: "block", maxWidth: g.width, minWidth: 720 }}>
          <defs>
            {[["n", pal.muted], ["c", pal.critical]].map(([id, color]) => (
              <marker key={id} id={`arrow-${id}`} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="8" markerHeight="8"
                      markerUnits="userSpaceOnUse" orient="auto-start-reverse">
                <path d="M 0 0 L 10 5 L 0 10 z" fill={color} />
              </marker>
            ))}
          </defs>
          {g.edges.map((e) => {
            const s = g.placed[e.source];
            const t = g.placed[e.target];
            const bad = e.flagged_share >= 0.5;
            return (
              <path key={`${e.source}-${e.target}`} d={edgePath(s, t)} fill="none"
                    stroke={bad ? pal.critical : pal.muted} strokeWidth={1 + 4 * Math.sqrt(e.count / maxCount)}
                    strokeOpacity={related(e) ? (bad ? 0.7 : 0.38) : 0.06} markerEnd={`url(#arrow-${bad ? "c" : "n"})`}>
                <title>{`${e.source} → ${e.target}: ${fmtInt(e.count)} transitions, ${fmtPct(e.flagged_share, 0)} in flagged runs`}</title>
              </path>
            );
          })}
          {Object.values(g.placed).map((n) => {
            const terminal = n.kind === "terminal";
            const unreg = n.kind === "unregistered";
            const fill = unreg ? "var(--critical-soft)" : terminal ? "var(--surface-2)" : "var(--surface)";
            const stroke = unreg ? pal.critical : n.error_rate > 0.2 ? pal.warning : "var(--border-strong)";
            return (
              <g key={n.id} transform={`translate(${n.x},${n.y})`} onMouseEnter={() => setHover(n.id)} onMouseLeave={() => setHover(null)}
                 style={{ cursor: "default", opacity: hover && hover !== n.id && !g.edges.some((e) => (e.source === hover && e.target === n.id) || (e.target === hover && e.source === n.id)) ? 0.35 : 1 }}>
                <rect width={W} height={H} rx={6} style={{ fill }} stroke={stroke} strokeWidth={unreg ? 1.5 : 1} />
                <text x={10} y={19} style={{ fill: "var(--text)", fontSize: 12.5, fontWeight: 600, fontFamily: terminal ? "inherit" : "ui-monospace, Consolas, monospace" }}>
                  {n.id.length > 19 ? `${n.id.slice(0, 18)}…` : n.id}
                </text>
                <text x={10} y={36} style={{ fill: "var(--text-2)", fontSize: 11 }}>
                  {terminal ? `${fmtInt(n.calls)} runs` : `${fmtInt(n.calls)} calls · ${fmtPct(n.error_rate, 0)} err`}
                </text>
                <title>{terminal ? n.id : `${n.id}\n${fmtInt(n.calls)} calls\nError rate ${fmtPct(n.error_rate)}\nAvg latency ${fmtInt(n.avg_latency_ms)} ms\n${fmtPct(n.flagged_share)} of calls in flagged runs${unreg ? "\nNOT a registered tool" : ""}`}</title>
              </g>
            );
          })}
        </svg>
      </div>
      <div className="legend">
        <span><span className="swatch" style={{ background: pal.muted, height: 3, width: 16 }} />Transition (width = volume)</span>
        <span><span className="swatch" style={{ background: pal.critical, height: 3, width: 16 }} />Mostly in flagged runs</span>
        <span><span className="swatch" style={{ background: "var(--critical-soft)", border: `1.5px solid ${pal.critical}` }} />Unregistered tool (hallucinated)</span>
        <span><span className="swatch" style={{ border: `1.5px solid ${pal.warning}` }} />Error rate above 20%</span>
      </div>
    </div>
  );
}
