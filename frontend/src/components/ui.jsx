import { createContext, useCallback, useContext, useRef, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import * as Tooltip from "@radix-ui/react-tooltip";
import { AlertCircle, Inbox, RefreshCw } from "lucide-react";
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

/** Placeholder blocks shaped like content, shown while data loads. */
export function Skeleton({ rows = 4 }) {
  return (
    <div className="skeleton" aria-busy="true" aria-label="Loading">
      <div className="sk-tiles">{[0, 1, 2, 3].map((i) => <div key={i} className="sk sk-tile" />)}</div>
      {Array.from({ length: rows }, (_, i) => <div key={i} className="sk sk-line" style={{ width: `${92 - i * 9}%` }} />)}
    </div>
  );
}

export const Loading = () => <Skeleton rows={3} />;

export function EmptyState({ icon: Icon = Inbox, title, children, action }) {
  return (
    <div className="empty-state">
      <div className="empty-icon"><Icon size={22} strokeWidth={1.75} /></div>
      {title && <div className="empty-title">{title}</div>}
      {children && <div className="empty-body">{children}</div>}
      {action && <div style={{ marginTop: 12 }}>{action}</div>}
    </div>
  );
}

export const Empty = ({ children = "No data for this selection." }) => <EmptyState>{children}</EmptyState>;

export function ErrorBox({ error, onRetry }) {
  return (
    <div className="error-box" role="alert">
      <div className="row" style={{ gap: 8, flexWrap: "nowrap", alignItems: "flex-start" }}>
        <AlertCircle size={18} style={{ flex: "none", marginTop: 1 }} />
        <div style={{ flex: 1 }}>
          <strong>Could not load data.</strong> {String(error?.message || error)}
          <div className="small" style={{ marginTop: 4 }}>
            Check that the API is running (<code>uvicorn app.main:app --port 8000</code> in <code>backend/</code>).
          </div>
        </div>
        {onRetry && <button onClick={onRetry} className="btn-icon-text"><RefreshCw size={14} /> Retry</button>}
      </div>
    </div>
  );
}

export function Async({ state, children, skeleton }) {
  if (state.error && !state.data) return <ErrorBox error={state.error} onRetry={state.reload} />;
  if (!state.data) return skeleton || <Loading />;
  return children(state.data);
}

/** Hover/focus tooltip. */
export function Tip({ label, children, side = "top" }) {
  return (
    <Tooltip.Root delayDuration={250}>
      <Tooltip.Trigger asChild>{children}</Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Content className="tooltip" side={side} sideOffset={6}>{label}</Tooltip.Content>
      </Tooltip.Portal>
    </Tooltip.Root>
  );
}

// ---------------------------------------------------------------- confirm dialog
const ConfirmContext = createContext(null);
export const useConfirm = () => useContext(ConfirmContext);

/** Accessible replacement for window.confirm: `if (await confirm({...})) ...` */
export function ConfirmProvider({ children }) {
  const [opts, setOpts] = useState(null);
  const resolver = useRef(null);
  const confirm = useCallback((o) => new Promise((resolve) => { resolver.current = resolve; setOpts(o); }), []);
  const close = (v) => { resolver.current?.(v); setOpts(null); };
  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      <Dialog.Root open={!!opts} onOpenChange={(o) => !o && close(false)}>
        <Dialog.Portal>
          <Dialog.Overlay className="dialog-overlay" />
          <Dialog.Content className="dialog">
            <Dialog.Title className="dialog-title">{opts?.title}</Dialog.Title>
            <Dialog.Description className="dialog-body">{opts?.body}</Dialog.Description>
            <div className="dialog-actions">
              {/* Destructive actions start focused on Cancel, so a stray Enter is harmless. */}
              <button onClick={() => close(false)} autoFocus={!!opts?.danger}>Cancel</button>
              <button className={opts?.danger ? "danger" : "primary"} onClick={() => close(true)} autoFocus={!opts?.danger}>
                {opts?.confirmLabel || "Confirm"}
              </button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </ConfirmContext.Provider>
  );
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
