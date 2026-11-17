import { useEffect, useState, useSyncExternalStore } from "react";

// Chart colors. Recharts takes colors as SVG attributes (no CSS variables),
// so light/dark values live here and the hook picks the current set.
const LIGHT = {
  series: ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"],
  good: "#0ca30c", warning: "#fab219", critical: "#d03b3b",
  grid: "#e1e0d9", axis: "#c3c2b7", text: "#52514e", muted: "#898781", surface: "#fcfcfb",
  neutral: "#b9b7ae", seq: ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"],
  div: { neg: "#d03b3b", mid: "#f0efec", pos: "#2a78d6" },
};
const DARK = {
  series: ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"],
  good: "#0ca30c", warning: "#fab219", critical: "#d03b3b",
  grid: "#2c2c2a", axis: "#45453f", text: "#c3c2b7", muted: "#898781", surface: "#1a1a19",
  neutral: "#5d5c57", seq: ["#1b2a3d", "#184f95", "#1c5cab", "#256abf", "#3987e5", "#6da7ec", "#b7d3f6"],
  div: { neg: "#e66767", mid: "#383835", pos: "#3987e5" },
};

// Fixed identity colors: an entity keeps its color on every chart.
export const FAILURE_ORDER = ["loop", "tool_thrashing", "hallucinated_tool", "token_waste", "novel_anomaly"];
export const FAILURE_LABEL = {
  loop: "Loop",
  tool_thrashing: "Tool thrashing",
  hallucinated_tool: "Hallucinated tool",
  token_waste: "Token waste",
  novel_anomaly: "Novel anomaly",
  healthy: "Healthy",
};
export const APPROACH_ORDER = ["Rules only", "Unsupervised only", "Supervised only", "Fused engine"];

function query() {
  return typeof window !== "undefined" && window.matchMedia
    ? window.matchMedia("(prefers-color-scheme: dark)")
    : null;
}

// Theme mode: "system" | "light" | "dark", remembered per browser.
const THEME_KEY = "aobs-theme";
const listeners = new Set();
function readMode() {
  try { return localStorage.getItem(THEME_KEY) || "system"; } catch { return "system"; }
}
let mode = readMode();
function applyMode() {
  const root = document.documentElement;
  if (mode === "system") root.removeAttribute("data-theme"); else root.setAttribute("data-theme", mode);
}
if (typeof document !== "undefined") applyMode();

export function setThemeMode(next) {
  mode = next;
  try { localStorage.setItem(THEME_KEY, next); } catch { /* storage blocked: still applies for this session */ }
  applyMode();
  listeners.forEach((l) => l());
}
const subscribe = (l) => { listeners.add(l); return () => listeners.delete(l); };
export const useThemeMode = () => useSyncExternalStore(subscribe, () => mode);

export function usePalette() {
  const current = useThemeMode();
  const [systemDark, setSystemDark] = useState(() => !!query()?.matches);
  useEffect(() => {
    const q = query();
    if (!q) return undefined;
    const fn = (e) => setSystemDark(e.matches);
    q.addEventListener("change", fn);
    return () => q.removeEventListener("change", fn);
  }, []);
  const dark = current === "dark" || (current === "system" && systemDark);
  const p = dark ? DARK : LIGHT;
  return {
    ...p,
    dark,
    failure: (t) => (t === "novel_anomaly" ? p.series[6] : p.series[FAILURE_ORDER.indexOf(t)] || p.neutral),
    approach: (a) => p.series[APPROACH_ORDER.indexOf(a)] || p.neutral,
    severity: (s) => ({ healthy: p.good, warning: p.warning, critical: p.critical })[s] || p.neutral,
    agent: (id, ids) => p.series[Math.max(0, ids.indexOf(id)) % p.series.length],
  };
}

export const axisProps = (pal) => ({
  stroke: pal.axis,
  tick: { fill: pal.muted, fontSize: 11.5 },
  tickLine: false,
});
