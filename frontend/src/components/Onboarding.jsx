import { Link } from "react-router-dom";
import { Check } from "lucide-react";
import { useApi } from "../api";
import { Card } from "./ui";

/** Setup checklist for new workspaces; disappears once every step is done. */
export default function Onboarding() {
  const creds = useApi("/api/workspace/credentials");
  const keys = useApi("/api/workspace/api-keys");
  const contracts = useApi("/api/llm/contracts");
  const rules = useApi("/api/llm/alert-rules");
  const calls = useApi("/api/llm/calls?limit=1");   // any call ever, not just this time window
  if ([creds, keys, contracts, rules, calls].some((s) => !s.data)) return null;
  const hasCalls = calls.data.total > 0;

  const steps = [
    { done: creds.data.length > 0, label: "Add a provider key (OpenAI, Claude or Gemini)", to: "/settings?tab=providers" },
    { done: keys.data.length > 0, label: "Create a workspace API key for your app or the browser extension", to: "/settings?tab=api-keys" },
    { done: hasCalls, label: "Send your first call through the gateway or extension", to: "/llm/connect" },
    { done: contracts.data.length > 0, label: "Write a prompt contract with the rules your answers must follow", to: "/llm/contracts?id=new" },
    { done: rules.data.length > 0, label: "Add an alert rule so problems reach you", to: "/llm/alerts" },
  ];
  const left = steps.filter((s) => !s.done).length;
  if (left === 0) return null;
  return (
    <Card title="Get set up" sub={`${steps.length - left} of ${steps.length} done`} style={{ marginBottom: 16 }}>
      <ul className="checklist">
        {steps.map((s) => (
          <li key={s.label} className={s.done ? "done" : ""}>
            <span className="tick" aria-hidden="true">{s.done && <Check size={12} strokeWidth={3} />}</span>
            {s.done ? <span className="t">{s.label}</span> : <Link to={s.to}>{s.label}</Link>}
            <span className="sr-only">{s.done ? "(done)" : "(to do)"}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}
