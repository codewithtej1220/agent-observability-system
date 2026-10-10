export const fmtInt = (n) => (n == null ? "–" : Math.round(n).toLocaleString());

export function fmtCompact(n) {
  if (n == null) return "–";
  const a = Math.abs(n);
  if (a >= 1e9) return `${(n / 1e9).toFixed(1)}B`;
  if (a >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  if (a >= 1e4) return `${(n / 1e3).toFixed(1)}K`;
  return Math.round(n).toLocaleString();
}

export const fmtPct = (x, d = 1) => (x == null ? "–" : `${(x * 100).toFixed(d)}%`);
export const fmtUsd = (x, d = 2) => (x == null ? "–" : `$${x.toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d })}`);
export const fmtNum = (x, d = 2) => (x == null ? "–" : Number(x).toFixed(d));

export function fmtTime(iso, withDate = true) {
  if (!iso) return "–";
  const d = new Date(iso);
  return withDate
    ? d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })
    : d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

export function fmtAgo(iso) {
  if (!iso) return "–";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export const humanize = (s) => (s ? s.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase()) : "–");
export const shortId = (id) => (id ? id.slice(0, 8) : "");
