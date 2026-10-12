export const PROVIDER_LABEL = { openai: "OpenAI", anthropic: "Anthropic", gemini: "Gemini" };

const SEV = { ok: ["healthy", "✓", "Passed"], warning: ["warning", "!", "Warning"], critical: ["critical", "✕", "Critical"] };

export function CallSeverity({ severity }) {
  const [cls, icon, label] = SEV[severity] || SEV.ok;
  return <span className={`badge ${cls}`}><span aria-hidden="true">{icon}</span>{label}</span>;
}

const ENF = {
  passed: ["info", "Checked"],
  repaired: ["warning", "Repaired"],
  fallback: ["warning", "Fallback model"],
  blocked: ["critical", "Blocked"],
};

export function EnforcementBadge({ action }) {
  if (!action || action === "none") return null;
  const [cls, label] = ENF[action] || ["neutral", action];
  return <span className={`badge ${cls}`}>{label}</span>;
}
