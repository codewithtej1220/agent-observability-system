import { usePalette } from "../theme";

const BOX_W = 168;
const BOX_H = 58;

function Box({ x, y, title, lines, tone }) {
  const stroke = tone ? tone : "var(--border-strong)";
  return (
    <g transform={`translate(${x},${y})`}>
      <rect width={BOX_W} height={BOX_H} rx={6} style={{ fill: "var(--surface)" }} stroke={stroke} strokeWidth={tone ? 1.5 : 1} />
      <text x={10} y={20} style={{ fill: "var(--text)", fontSize: 12.5, fontWeight: 600 }}>{title}</text>
      {lines.map((l, i) => (
        <text key={i} x={10} y={37 + i * 13} style={{ fill: "var(--text-2)", fontSize: 11 }}>{l}</text>
      ))}
    </g>
  );
}

/** Static flowchart of the detection + intervention pipeline. */
export default function PipelineDiagram() {
  const pal = usePalette();
  const c = (x) => x + BOX_W / 2;
  const m = (y) => y + BOX_H / 2;
  const X = [10, 220, 430, 640, 850];
  const Y = [20, 100, 180];
  const arrow = (x1, y1, x2, y2, key, color = pal.muted) => {
    const dx = (x2 - x1) * 0.5;
    return <path key={key} d={`M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2 - 4} ${y2}`} fill="none" stroke={color} strokeWidth={1.5} markerEnd="url(#pd-arrow)" />;
  };

  return (
    <div className="table-wrap">
      <svg width={1030} height={300} role="img" aria-label="Detection pipeline diagram" style={{ display: "block" }}>
        <defs>
          <marker id="pd-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill={pal.muted} />
          </marker>
        </defs>
        <Box x={X[0]} y={Y[1]} title="Agent step" lines={["tool call, reasoning", "or final answer (SDK)"]} />
        <Box x={X[1]} y={Y[1]} title="Behavioral features" lines={["repetition, cycles, errors,", "novelty, spend vs baseline"]} />
        <Box x={X[2]} y={Y[0]} title="Rule detectors" lines={["explainable, exact", "step-level evidence"]} tone={pal.series[0]} />
        <Box x={X[2]} y={Y[1]} title="Unsupervised" lines={["IsolationForest + k-NN", "HDBSCAN archetypes"]} tone={pal.series[1]} />
        <Box x={X[2]} y={Y[2]} title="Supervised classifier" lines={["gradient boosting on", "run prefixes (early)"]} tone={pal.series[2]} />
        <Box x={X[3]} y={Y[1]} title="Fusion + open-set gate" lines={["learned weights; flags", "unseen failure types"]} />
        <Box x={X[4]} y={Y[0] + 40} title="Risk + failure type" lines={["severity, evidence,", "class probabilities"]} />
        <Box x={X[4]} y={Y[2] - 40} title="LinUCB policy" lines={["chooses intervention", "with guardrails"]} tone={pal.series[3]} />
        {arrow(X[0] + BOX_W, m(Y[1]), X[1], m(Y[1]), "a1")}
        {[0, 1, 2].map((i) => arrow(X[1] + BOX_W, m(Y[1]), X[2], m(Y[i]), `f${i}`))}
        {arrow(X[2] + BOX_W, m(Y[0]), X[3], m(Y[1]) - 10, "r")}
        {arrow(X[2] + BOX_W, m(Y[1]), X[3], m(Y[1]), "u")}
        {arrow(X[2] + BOX_W, m(Y[2]), X[3], m(Y[1]) + 10, "s")}
        {/* stacking: rule + novelty outputs are classifier inputs */}
        <path d={`M ${c(X[2]) - 40} ${Y[1] + BOX_H} L ${c(X[2]) - 40} ${Y[2] - 4}`} stroke={pal.muted} strokeWidth={1} fill="none" markerEnd="url(#pd-arrow)" />
        <path d={`M ${c(X[2]) + 40} ${Y[0] + BOX_H} L ${c(X[2]) + 40} ${Y[1] - 4}`} stroke={pal.muted} strokeWidth={1} fill="none" markerEnd="url(#pd-arrow)" />
        {arrow(X[3] + BOX_W, m(Y[1]), X[4], m(Y[0] + 40), "o1")}
        {arrow(X[3] + BOX_W, m(Y[1]), X[4], m(Y[2] - 40), "o2")}
        {/* feedback loop */}
        <path d={`M ${c(X[4])} ${Y[2] - 40 + BOX_H} L ${c(X[4])} 275 L ${c(X[2])} 275 L ${c(X[2])} ${Y[2] + BOX_H + 4}`}
              fill="none" stroke={pal.series[3]} strokeWidth={1.5} markerEnd="url(#pd-arrow)" />
        <text x={c(X[3]) - 30} y={290} style={{ fill: "var(--text-2)", fontSize: 11.5 }}>
          Human review: outcome → policy reward · label → classifier retrain
        </text>
        <text x={c(X[2]) - 112} y={Y[2] - 8} style={{ fill: "var(--muted)", fontSize: 10.5 }}>stacked inputs</text>
      </svg>
    </div>
  );
}
