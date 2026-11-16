import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { queryClient } from "./api";

const BASE = import.meta.env.VITE_API_BASE || "";
const REFRESH_EVERY_MS = 2000; // a burst of calls refreshes the screen at most this often

/**
 * Live updates over server-sent events (/api/stream).
 * New calls, alerts and flagged agent runs refresh the visible pages and raise
 * toasts for anything that needs attention. Returns "live" | "connecting" | "offline".
 */
export function useRealtime(onOpenLink) {
  const [status, setStatus] = useState("connecting");
  const pending = useRef(null);
  const linkRef = useRef(onOpenLink);
  linkRef.current = onOpenLink;

  useEffect(() => {
    if (typeof EventSource === "undefined") {
      setStatus("offline");
      return undefined;
    }
    const es = new EventSource(`${BASE}/api/stream`, { withCredentials: true });
    const refresh = (prefix) => {
      if (pending.current) return;
      pending.current = setTimeout(() => {
        pending.current = null;
        queryClient.invalidateQueries({
          predicate: (q) => q.queryKey[0] === "api" && typeof q.queryKey[1] === "string"
            && (!prefix || prefix.some((p) => q.queryKey[1].startsWith(p))),
        });
      }, REFRESH_EVERY_MS);
    };
    const parse = (e) => { try { return JSON.parse(e.data); } catch { return {}; } };

    es.onopen = () => setStatus("live");
    es.onerror = () => setStatus(es.readyState === EventSource.CLOSED ? "offline" : "connecting");
    es.addEventListener("call", (e) => {
      const c = parse(e);
      refresh(["/api/llm", "/api/billing"]);
      if (c.severity === "critical") {
        toast.error(`Critical: ${c.failed_checks?.[0] || "check failed"}`, {
          description: `${c.provider} · ${c.model}${c.enforcement_action && c.enforcement_action !== "none" ? ` · ${c.enforcement_action}` : ""}`,
          action: { label: "Open", onClick: () => linkRef.current?.(`/llm/calls/${c.id}`) },
        });
      }
    });
    es.addEventListener("alert", (e) => {
      const a = parse(e);
      refresh(["/api/llm/alerts", "/api/billing"]);
      (a.severity === "critical" ? toast.error : toast.warning)(a.title || "New alert", {
        action: { label: "View", onClick: () => linkRef.current?.(a.ref_type === "llm_call" && a.ref_id ? `/llm/calls/${a.ref_id}` : "/llm/alerts") },
      });
    });
    es.addEventListener("run", (e) => {
      const r = parse(e);
      refresh(["/api/overview", "/api/runs", "/api/review-queue", "/api/agents"]);
      if (r.severity === "critical") {
        toast.error(`Agent run flagged: ${(r.failure_type || "anomaly").replace(/_/g, " ")}`, {
          description: r.agent_id,
          action: { label: "Open", onClick: () => linkRef.current?.(`/runs/${r.id}`) },
        });
      }
    });
    return () => {
      es.close();
      clearTimeout(pending.current);
      pending.current = null;
    };
  }, []);

  return status;
}
