import { FAILURE_LABEL, usePalette } from "../theme";
import { humanize } from "../format";

export function Card({ title, sub, right, children, className = "", flush = false, style }) {
  return (
    <section className={`card ${flush ? "flush" : ""} ${className}`} style={style}>
      {(title || right) && (
        <div className="card-head">
          <div>
            {title && <h2>{title}</h2>}
            {sub && <div className="sub">{sub}</div>}
          </div>
          {right}
        </div>
      )}
      {children}
    </section>
  );
}

export function Tile({ label, value, delta, deltaGood, hint }) {
  const cls = deltaGood == null ? "" : deltaGood ? "good" : "bad";
  return (
    <div className="tile" title={hint}>
      <div className="tile-label">{label}</div>
      <div className="tile-value">{value}</div>
      {delta && <div className={`tile-delta ${cls}`}>{delta}</div>}
    </div>
  );
}

const SEV_ICON = { healthy: "✓", warning: "!", critical: "✕" };

export function SeverityBadge({ severity }) {
  return (
    <span className={`badge ${severity}`}>
      <span aria-hidden="true">{SEV_ICON[severity]}</span>
      {humanize(severity)}
    </span>
  );
}

export function FailureTag({ type, muted = false }) {
  const pal = usePalette();
  if (!type) return <span className="muted">–</span>;
  return (
    <span className="tag">
      <span className="swatch" style={{ background: muted ? pal.neutral : pal.failure(type) }} />
      {FAILURE_LABEL[type] || humanize(type)}
    </span>
  );
}

export function Meter({ value, color, max = 1, width }) {
  const pal = usePalette();
  const pct = Math.max(0, Math.min(1, (value || 0) / max)) * 100;
  return (
    <div className="meter" style={{ width }}>
      <div style={{ width: `${pct}%`, background: color || pal.series[0] }} />
    </div>
  );
}

export function RiskMeter({ risk }) {
  const pal = usePalette();
  const color = risk >= 0.7 ? pal.critical : risk >= 0.35 ? pal.warning : pal.good;
  return (
    <div className="row" style={{ gap: 8, flexWrap: "nowrap" }}>
      <Meter value={risk} color={color} width={56} />
      <span className="num small">{risk.toFixed(2)}</span>
    </div>
  );
}

export const Loading = () => <div className="empty">Loading…</div>;
export const Empty = ({ children = "No data for this selection." }) => <div className="empty">{children}</div>;

export function ErrorBox({ error }) {
  return (
    <div className="error-box">
      <strong>Could not load data.</strong> {String(error?.message || error)}
      <div className="small" style={{ marginTop: 4 }}>
        Is the API running on port 8000 and have models been bootstrapped? (<code>python -m scripts.bootstrap</code>)
      </div>
    </div>
  );
}

export function Async({ state, children }) {
  if (state.error && !state.data) return <ErrorBox error={state.error} />;
  if (!state.data) return <Loading />;
  return children(state.data);
}

export function ChartTip({ active, payload, label, labelFormatter, valueFormatter = (v) => v, names = {} }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="chart-tip">
      {label != null && <div className="t">{labelFormatter ? labelFormatter(label) : label}</div>}
      {payload.map((p) => (
        <div className="r" key={p.dataKey ?? p.name}>
          <span className="tag">
            <span className="swatch" style={{ background: p.color || p.fill || p.stroke }} />
            {names[p.dataKey] || p.name}
          </span>
          <strong className="num">{valueFormatter(p.value, p)}</strong>
        </div>
      ))}
    </div>
  );
}

export function Legend({ items }) {
  return (
    <div className="legend">
      {items.map((it) => (
        <span key={it.label}>
          <span className="swatch" style={{ background: it.color, ...(it.line ? { height: 2, width: 14 } : {}) }} />
          {it.label}
        </span>
      ))}
    </div>
  );
}

export function Segmented({ options, value, onChange }) {
  return (
    <div className="seg" role="group">
      {options.map((o) => (
        <button key={o.value} className={o.value === value ? "on" : ""} onClick={() => onChange(o.value)} type="button">
          {o.label}
        </button>
      ))}
    </div>
  );
}

export const RANGES = [
  { value: 24, label: "24h" },
  { value: 72, label: "3d" },
  { value: 168, label: "7d" },
];

export function Pager({ total, limit, offset, onChange }) {
  const page = Math.floor(offset / limit) + 1;
  const pages = Math.max(1, Math.ceil(total / limit));
  return (
    <div className="spread small" style={{ padding: "10px 16px" }}>
      <span className="muted">{total.toLocaleString()} runs</span>
      <div className="row">
        <button disabled={page <= 1} onClick={() => onChange(offset - limit)}>Previous</button>
        <span className="num">Page {page} of {pages}</span>
        <button disabled={page >= pages} onClick={() => onChange(offset + limit)}>Next</button>
      </div>
    </div>
  );
}
