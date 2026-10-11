import { useCallback, useEffect, useRef, useState } from "react";

const BASE = import.meta.env.VITE_API_BASE || "";
const KEY = import.meta.env.VITE_API_KEY || "dev-local-key";

export async function api(path, { method = "GET", body } = {}) {
  const url = `${BASE}${path}`;
  let res;
  try {
    res = await fetch(url, {
      method,
      headers: { "X-API-Key": KEY, ...(body ? { "Content-Type": "application/json" } : {}) },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    // Network-level failure: server down/restarting, wrong host, or blocked by CORS.
    throw new Error(`Cannot reach the API at ${BASE || window.location.origin}${path.split("?")[0]}`);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const j = await res.json();
      detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch { /* not JSON */ }
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json();
}

/** Fetch `path` (re-fetching when it changes, and every `refreshMs` if set). */
export function useApi(path, { refreshMs = 0 } = {}) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  const current = useRef(path);
  current.current = path;

  const load = useCallback(async () => {
    if (!path) return;
    try {
      const data = await api(path);
      if (current.current === path) setState({ data, error: null, loading: false });
    } catch (error) {
      if (current.current === path) setState((s) => ({ ...s, error, loading: false }));
    }
  }, [path]);

  useEffect(() => {
    setState((s) => ({ ...s, loading: true }));
    load();
    if (!refreshMs) return undefined;
    const id = setInterval(load, refreshMs);
    return () => clearInterval(id);
  }, [load, refreshMs]);

  return { ...state, reload: load };
}
