import { useCallback, useEffect, useRef, useState } from "react";

// Same-origin by default: the dev server and nginx proxy /api to the backend.
const BASE = import.meta.env.VITE_API_BASE || "";

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

export async function api(path, { method = "GET", body } = {}) {
  const url = `${BASE}${path}`;
  let res;
  try {
    res = await fetch(url, {
      method,
      credentials: "include",
      headers: { "X-Requested-With": "aobs", ...(body !== undefined ? { "Content-Type": "application/json" } : {}) },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    // Network-level failure: server down/restarting, wrong host, or blocked by CORS.
    throw new ApiError(0, `Cannot reach the API at ${BASE || window.location.origin}${path.split("?")[0]}`);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const j = await res.json();
      if (typeof j.detail === "string") detail = j.detail;
      else if (Array.isArray(j.detail)) {
        // FastAPI validation errors: "email: value is not a valid email address: …"
        detail = j.detail.map((e) => `${(e.loc || []).filter((p) => p !== "body").join(".")}: ${e.msg}`).join("; ");
      } else detail = j.error?.message || detail;
    } catch { /* not JSON */ }
    if (res.status === 401) window.dispatchEvent(new Event("aobs:unauthorized"));
    throw new ApiError(res.status, detail);
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
    // A different request: drop the previous result so it is never shown under new filters.
    setState({ data: null, error: null, loading: true });
    load();
    if (!refreshMs) return undefined;
    const id = setInterval(load, refreshMs);
    return () => clearInterval(id);
  }, [load, refreshMs]);

  return { ...state, reload: load };
}
