import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Check, Eye } from "lucide-react";
import { api, useApi } from "../api";
import { Async, Card } from "../components/ui";
import { fmtInt, fmtTime } from "../format";

const fmtLimit = (n) => (n == null ? "Unlimited" : fmtInt(n));
const STATUS_LABEL = { active: "Active", trialing: "Trial", past_due: "Payment due", canceled: "Canceled" };

const COMPARE_ROWS = [
  ["Tracked LLM calls / month", (p) => fmtLimit(p.llm_calls_month)],
  ["Agent runs / month", (p) => fmtLimit(p.agent_runs_month)],
  ["Members", (p) => fmtLimit(p.seats)],
  ["Prompt contracts", (p) => fmtLimit(p.contracts)],
  ["Alert rules", (p) => fmtLimit(p.alert_rules)],
  ["Drift tests", (p) => fmtLimit(p.drift_tests)],
  ["Content retention", (p) => `${p.retention_days} days`],
  ["Requests / minute", (p) => fmtInt(p.rate_per_min)],
  ["Built-in checks, ML detection, browser extension", () => true],
  ["LLM judge", (p) => p.judge],
  ["Block, repair and auto-correct", (p) => p.enforcement],
  ["Slack, webhook and email alerts", (p) => p.channels.includes("slack")],
];

function Cell({ v }) {
  if (v === true) return <Check size={16} style={{ color: "var(--good)" }} aria-label="Included" />;
  if (v === false) return <span className="muted" aria-label="Not included">–</span>;
  return <span className="num">{v}</span>;
}

/** Plan cards + comparison table. `action(plan)` renders the button under each card. */
export function PlanTable({ plans, current, action }) {
  return (
    <>
      <div className="grid plan-cards" style={{ gridTemplateColumns: `repeat(${plans.length}, minmax(0, 1fr))`, maxWidth: plans.length < 3 ? 900 : undefined }}>
        {plans.map((p) => (
          <div key={p.id} className={`card plan-card ${current === p.id ? "current" : ""}`}>
            <div className="spread">
              <h2>{p.name}</h2>
              {current === p.id && <span className="badge info">Current plan</span>}
            </div>
            <div className="plan-price">
              <span className="num">${p.price_month}</span><span className="muted small"> / month</span>
            </div>
            <div className="muted small" style={{ minHeight: 34 }}>{p.tagline}</div>
            <ul className="plan-highlights">
              {p.highlights.map((h) => <li key={h}><Check size={14} /> {h}</li>)}
            </ul>
            <div style={{ marginTop: "auto" }}>{action?.(p)}</div>
          </div>
        ))}
      </div>
      <Card title="Compare plans" flush style={{ marginTop: 16 }}>
        <div className="table-wrap">
          <table>
            <thead><tr><th></th>{plans.map((p) => <th key={p.id} className="r">{p.name}</th>)}</tr></thead>
            <tbody>
              {COMPARE_ROWS.map(([label, fn]) => (
                <tr key={label}><td>{label}</td>{plans.map((p) => <td key={p.id} className="r"><Cell v={fn(p)} /></td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}

function UsageRow({ label, used, limit, hint }) {
  const pct = limit ? Math.min(1, used / limit) : 0;
  const color = pct >= 1 ? "var(--critical)" : pct >= 0.8 ? "var(--warning)" : "var(--accent)";
  return (
    <div className="usage-row">
      <div className="spread small">
        <span>{label}</span>
        <span className="num">{fmtInt(used)} <span className="muted">/ {fmtLimit(limit)}</span></span>
      </div>
      <div className="meter" role="progressbar" aria-label={label} aria-valuenow={Math.round(pct * 100)} aria-valuemin={0} aria-valuemax={100}>
        <div style={{ width: `${limit ? pct * 100 : 0}%`, background: color }} />
      </div>
      {hint && <div className="small muted">{hint}</div>}
    </div>
  );
}

export function BillingTab() {
  const billing = useApi("/api/billing");
  const [params, setParams] = useSearchParams();
  const [busy, setBusy] = useState(null);

  useEffect(() => {
    const result = params.get("checkout");
    if (!result) return;
    if (result === "success") toast.success("Subscription started. It can take a few seconds to show here.");
    else toast("Checkout canceled. Your plan has not changed.");
    params.delete("checkout");
    setParams(params, { replace: true });
  }, [params, setParams]);

  const go = async (key, path, body) => {
    setBusy(key);
    try {
      const r = await api(path, { method: "POST", body });
      if (r.url) window.location.assign(r.url);
      else toast.success("Plan updated");
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <Async state={billing}>
      {(b) => {
        const u = b.usage, l = b.limits;
        const paid = b.subscribed_plan !== "free" && b.status !== "trialing";
        const action = (p) => {
          if (!b.can_manage) return <div className="small muted">Ask a workspace admin to change the plan.</div>;
          if (p.id === b.plan.id) {
            return b.has_billing_account && b.online_billing
              ? <button onClick={() => go("portal", "/api/billing/portal")} disabled={busy}>Manage billing</button>
              : <button disabled>Current plan</button>;
          }
          if (p.id === "free") {
            return paid && b.online_billing
              ? <button onClick={() => go("portal", "/api/billing/portal")} disabled={busy}>Downgrade in billing portal</button>
              : null;
          }
          if (paid && b.online_billing) {
            return <button onClick={() => go("portal", "/api/billing/portal")} disabled={busy}>Change in billing portal</button>;
          }
          return (
            <div className="stack" style={{ gap: 8 }}>
              {b.online_billing
                ? <button className="primary" onClick={() => go(p.id, "/api/billing/checkout", { plan: p.id })} disabled={busy}>
                    {busy === p.id ? "Opening checkout…" : `Upgrade to ${p.name}`}
                  </button>
                : <div className="small muted">Online payments are not set up on this server; the platform owner can change your plan.</div>}
              {p.id === "pro" && b.trial_available && (
                <button onClick={() => go("trial", "/api/billing/trial")} disabled={busy}>Start {b.trial_days}-day free trial</button>
              )}
            </div>
          );
        };
        return (
          <div className="stack" style={{ gap: 16 }}>
            <div className="grid cols-3">
              <Card title={`${b.plan.name} plan`} sub={b.plan.tagline}
                    right={<span className={`badge ${b.status === "past_due" ? "warning" : "neutral"}`}>{STATUS_LABEL[b.status] || b.status}</span>}>
                <div className="kv small">
                  {b.status === "trialing" && b.trial_ends_at && <><span>Trial ends</span><span>{fmtTime(b.trial_ends_at)}</span></>}
                  {b.current_period_end && <><span>Renews</span><span>{fmtTime(b.current_period_end, true)}</span></>}
                  <span>Billing period</span><span>{b.period}</span>
                  <span>Retention</span><span>{b.plan.retention_days} days</span>
                </div>
                {b.status === "past_due" && (
                  <div className="error-box small" style={{ marginTop: 10 }}>
                    The last payment failed. Update your card in the billing portal to keep paid features.
                  </div>
                )}
              </Card>
              <Card title="Usage this month" className="span-2">
                <div className="grid cols-2" style={{ gap: 14 }}>
                  <UsageRow label="Tracked LLM calls" used={u.llm_calls} limit={l.llm_calls}
                            hint={u.llm_calls_unanalyzed ? `${fmtInt(u.llm_calls_unanalyzed)} calls forwarded without analysis (over limit)` : null} />
                  <UsageRow label="Agent runs" used={u.agent_runs} limit={l.agent_runs} />
                  <UsageRow label="Members" used={u.seats} limit={l.seats} />
                  <UsageRow label="Prompt contracts" used={u.contracts} limit={l.contracts} />
                  <UsageRow label="Alert rules" used={u.alert_rules} limit={l.alert_rules} />
                  <UsageRow label="Drift tests" used={u.drift_tests} limit={l.drift_tests} />
                </div>
                <div className="note small" style={{ marginTop: 12 }}>
                  Over the monthly limit, the gateway keeps forwarding your traffic to the provider; it only stops checking
                  and storing calls until the next month or an upgrade. Your app never breaks because of a plan limit.
                </div>
              </Card>
            </div>
            {b.plan.id === "internal"
              ? <div className="note">This workspace is on the internal plan: no limits, every feature included.</div>
              : <PlanTable plans={b.plans} current={b.plan.id} action={action} />}
          </div>
        );
      }}
    </Async>
  );
}

/** Public pricing page (no sign-in needed). */
export function PricingPage() {
  const plans = useApi("/api/plans");
  return (
    <div className="pricing-shell">
      <div className="pricing-head">
        <Link to="/login" className="row" style={{ gap: 8, color: "var(--text)", textDecoration: "none" }}>
          <span className="brand-mark"><Eye size={16} /></span><strong>Agent Observability</strong>
        </Link>
        <div className="row" style={{ gap: 8 }}>
          <Link className="btn" to="/login">Sign in</Link>
          <Link className="btn primary" to="/signup">Start free</Link>
        </div>
      </div>
      <h1 style={{ marginBottom: 6 }}>Simple plans that grow with you</h1>
      <p className="muted" style={{ marginTop: 0, maxWidth: 640 }}>
        Monitor ChatGPT, Claude and Gemini, enforce prompt contracts, and catch agent loops and tool failures.
        Start free. Upgrade to Pro for $5 a month when you need enforcement, the LLM judge or more volume, with a 14-day free trial.
      </p>
      <Async state={plans}>
        {(d) => (
          <PlanTable plans={d.plans} action={(p) => (
            <Link className={`btn ${p.id === "pro" ? "primary" : ""}`} to="/signup" style={{ width: "100%", justifyContent: "center" }}>
              {p.id === "free" ? "Start free" : `Start with ${p.name}`}
            </Link>
          )} />
        )}
      </Async>
      <p className="small muted" style={{ marginTop: 16 }}>
        Prices in USD, billed monthly, cancel any time. Limits reset on the 1st of each month. Going over a limit never
        blocks your traffic: calls are still forwarded, just not analyzed.
      </p>
    </div>
  );
}
