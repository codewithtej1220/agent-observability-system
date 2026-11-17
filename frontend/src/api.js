import { QueryClient, useQuery } from "@tanstack/react-query";

// Same-origin by default: the dev server and nginx proxy /api to the backend.
const BASE = import.meta.env.VITE_API_BASE || "";

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 10_000,               // revisiting a page shows cached data instantly
      refetchOnWindowFocus: true,
      retry: (n, err) => (err?.status === 0 || err?.status >= 500) && n < 2,
    },
  },
});

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
    if (res.status === 402) window.dispatchEvent(new CustomEvent("aobs:plan-limit", { detail }));
    throw new ApiError(res.status, detail);
  }
  const data = await res.json();
  // Any successful change can affect any page: refresh what is on screen.
  if (method !== "GET") queryClient.invalidateQueries({ queryKey: ["api"] });
  return data;
}

/** Fetch `path` (cached; re-fetched every `refreshMs` if set). */
export function useApi(path, { refreshMs = 0 } = {}) {
  const q = useQuery({
    queryKey: ["api", path],
    queryFn: () => api(path),
    enabled: !!path,
    refetchInterval: refreshMs || false,
  });
  return { data: q.data ?? null, error: q.error, loading: q.isPending && !!path, fetching: q.isFetching, reload: q.refetch };
}
