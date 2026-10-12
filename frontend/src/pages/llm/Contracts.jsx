import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, useApi } from "../../api";
import { useAuth } from "../../auth";
import { Async, Card } from "../../components/ui";
import { fmtInt, fmtPct } from "../../format";

const EMPTY = { name: "", slug: "", description: "", rules: [], mode: "monitor", max_repairs: 1, fallback_models: [], judge_in_enforcement: false, active: true };

const PARAM_HELP = {
  json_schema: "JSON Schema, e.g. {\"type\": \"object\", \"required\": [\"answer\"]}",
  regex_required: "Regular expression the response must match",
  regex_forbidden: "Regular expression the response must not match",
  contains_all: "Comma-separated terms that must appear",
  contains_none: "Comma-separated terms that must not appear",
  llm_judge: "Plain-language rule for the judge, e.g. “Never promises a refund without a ticket number.”",
  relevance_min: "0–1; lexical overlap with the prompt (0.05 catches clearly off-topic answers)",
};

const MODE_HELP = {
  monitor: "Responses pass through unchanged; violations are logged and alerted on.",
  block: "Responses with a critical violation are replaced by an HTTP 422 error.",
  repair: "On a critical violation, the model is asked to fix its answer, then fallback models are tried, then the response is blocked.",
};

function slugify(s) {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 64);
}

export default function Contracts() {
  const [params, setParams] = useSearchParams();
  const list = useApi("/api/llm/contracts");
  const types = useApi("/api/llm/rule-types");
  const selected = params.get("id");
  const items = list.data || [];
  const current = selected === "new" ? null : items.find((c) => String(c.id) === selected);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Prompt contracts</h1>
          <p>
            A contract is the set of rules a project's responses must follow, and what happens when they don't. Apps opt in with the
            header <code>X-AOBS-Project: &lt;slug&gt;</code>. Critical rules are what block and repair modes enforce; warnings are only reported.
          </p>
        </div>
        <button className="primary" onClick={() => setParams({ id: "new" })}>New contract</button>
      </div>
      <div className="grid" style={{ gridTemplateColumns: "minmax(240px, 320px) minmax(0, 1fr)" }}>
        <Card flush title="Contracts">
          <Async state={list}>
            {() => items.length === 0 ? <div className="empty">No contracts yet.</div> : (
              <table>
                <tbody>
                  {items.map((c) => (
                    <tr key={c.id} className="clickable" onClick={() => setParams({ id: c.id })}
                        style={String(c.id) === selected ? { fontWeight: 600 } : undefined}>
                      <td>{c.name}<div className="small muted mono">{c.slug}</div></td>
                      <td className="small">{c.mode}{!c.active && <div className="muted">inactive</div>}</td>
                      <td className="r small">{c.stats_7d.calls ? fmtPct(c.stats_7d.adherence ?? 1) : "–"}<div className="muted">{fmtInt(c.stats_7d.calls)} calls</div></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Async>
        </Card>
        {selected ? (
          <Async state={types}>
            {(t) => <Editor key={selected} initial={current || EMPTY} isNew={!current} types={t} onSaved={(c) => { list.reload(); setParams({ id: c.id }); }}
                            onDeleted={() => { list.reload(); setParams({}); }} />}
          </Async>
        ) : <Card><div className="empty">Select a contract, or create one.</div></Card>}
      </div>
    </>
  );
}

function RuleEditor({ rule, types, onChange, onRemove }) {
  const spec = types.types.find((x) => x.type === rule.type);
  const setParam = (k, v) => onChange({ ...rule, params: { ...rule.params, [k]: v } });
  return (
    <div className="rule-card">
      <div className="spread" style={{ marginBottom: 8 }}>
        <strong className="small">{spec?.label}</strong>
        <div className="row">
          <select value={rule.severity} onChange={(e) => onChange({ ...rule, severity: e.target.value })}>
            <option value="critical">Critical (enforced)</option><option value="warning">Warning (report only)</option>
          </select>
          <button onClick={onRemove}>Remove</button>
        </div>
      </div>
      <div className="form-grid">
        {Object.entries(spec?.params || {}).map(([name, kind]) => (
          <label key={name} className={`field ${kind === "text" || kind === "object" ? "wide" : ""}`}>
            {name === "value" ? "Value" : name.replace(/_/g, " ")}
            {kind === "script" ? (
              <select value={rule.params[name] || ""} onChange={(e) => setParam(name, e.target.value)}>
                <option value="">Choose…</option>
                {types.scripts.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            ) : kind === "text" || kind === "object" ? (
              <textarea value={typeof rule.params[name] === "object" ? JSON.stringify(rule.params[name], null, 2) : rule.params[name] || ""}
                        onChange={(e) => setParam(name, e.target.value)} className={kind === "object" ? "mono" : ""} />
            ) : (
              <input type={kind === "int" || kind === "float" ? "number" : "text"} step={kind === "float" ? "0.01" : undefined}
                     value={Array.isArray(rule.params[name]) ? rule.params[name].join(", ") : rule.params[name] ?? ""}
                     onChange={(e) => setParam(name, e.target.value)} />
            )}
            {PARAM_HELP[rule.type] && <span className="muted">{PARAM_HELP[rule.type]}</span>}
          </label>
        ))}
        <label className="field wide">Label shown in reports
          <input type="text" value={rule.description || ""} onChange={(e) => onChange({ ...rule, description: e.target.value })} placeholder={spec?.label} />
        </label>
      </div>
    </div>
  );
}

function Editor({ initial, isNew, types, onSaved, onDeleted }) {
  const { can } = useAuth();
  const [c, setC] = useState(initial);
  const [addType, setAddType] = useState("json_valid");
  const [msg, setMsg] = useState(null);
  const [test, setTest] = useState({ system: "", user: "", response: "", use_judge: false });
  const [testResult, setTestResult] = useState(null);
  useEffect(() => setC(initial), [initial]);
  const set = (k, v) => setC({ ...c, [k]: v });
  const rules = c.rules || [];

  const payload = () => ({ ...c, fallback_models: (typeof c.fallback_models === "string" ? c.fallback_models.split(",") : c.fallback_models).map((s) => s.trim()).filter(Boolean),
                           max_repairs: Number(c.max_repairs) });
  const save = async () => {
    setMsg(null);
    try {
      const r = await api(isNew ? "/api/llm/contracts" : `/api/llm/contracts/${initial.id}`, { method: isNew ? "POST" : "PATCH", body: payload() });
      setMsg({ ok: true, text: "Saved" });
      onSaved(r);
    } catch (e) { setMsg({ ok: false, text: e.message }); }
  };
  const runTest = async () => {
    setTestResult(null);
    try { setTestResult(await api("/api/llm/contracts/test", { method: "POST", body: { ...test, rules } })); }
    catch (e) { setTestResult({ error: e.message }); }
  };

  return (
    <div className="stack">
      <Card title={isNew ? "New contract" : c.name}>
        <div className="form-grid">
          <label className="field">Name<input type="text" value={c.name} onChange={(e) => setC({ ...c, name: e.target.value, slug: isNew && (!c.slug || c.slug === slugify(c.name)) ? slugify(e.target.value) : c.slug })} /></label>
          <label className="field">Slug (X-AOBS-Project)<input type="text" className="mono" value={c.slug} onChange={(e) => set("slug", e.target.value)} /></label>
          <label className="field wide">Description<input type="text" value={c.description} onChange={(e) => set("description", e.target.value)} /></label>
          <label className="field">Mode
            <select value={c.mode} onChange={(e) => set("mode", e.target.value)}>
              <option value="monitor">Monitor</option><option value="block">Block</option><option value="repair">Repair</option>
            </select>
            <span className="muted">{MODE_HELP[c.mode]}</span>
          </label>
          {c.mode === "repair" && (
            <label className="field">Repair attempts<input type="number" min={0} max={3} value={c.max_repairs} onChange={(e) => set("max_repairs", e.target.value)} /></label>
          )}
          {c.mode !== "monitor" && (
            <>
              <label className="field">Fallback models (same provider)
                <input type="text" value={Array.isArray(c.fallback_models) ? c.fallback_models.join(", ") : c.fallback_models}
                       onChange={(e) => set("fallback_models", e.target.value)} placeholder="e.g. gpt-4.1, gpt-4o" />
                <span className="muted">Tried in order on provider errors or after failed repairs.</span>
              </label>
              <label className="check-row"><input type="checkbox" checked={c.judge_in_enforcement} onChange={(e) => set("judge_in_enforcement", e.target.checked)} />
                Enforce judge rules too (adds a judge call before responding)</label>
            </>
          )}
          <label className="check-row"><input type="checkbox" checked={c.active} onChange={(e) => set("active", e.target.checked)} /> Active</label>
        </div>
      </Card>

      <Card title="Rules" sub={`${rules.length} rule${rules.length === 1 ? "" : "s"}`}
            right={<div className="row">
              <select value={addType} onChange={(e) => setAddType(e.target.value)}>
                {types.types.map((t) => <option key={t.type} value={t.type}>{t.label}</option>)}
              </select>
              <button onClick={() => set("rules", [...rules, { id: `r${Date.now().toString(36)}`, type: addType, params: {}, severity: "critical", description: "" }])}>Add rule</button>
            </div>}>
        <div className="stack" style={{ gap: 10 }}>
          {rules.length === 0 && <div className="muted small">No rules yet. Built-in checks (PII, prompt injection, refusals, truncation, errors) always run.</div>}
          {rules.map((r, i) => (
            <RuleEditor key={r.id || i} rule={r} types={types}
                        onChange={(nr) => set("rules", rules.map((x, j) => (j === i ? nr : x)))}
                        onRemove={() => set("rules", rules.filter((_, j) => j !== i))} />
          ))}
        </div>
        <div className="row" style={{ marginTop: 14 }}>
          <button className="primary" onClick={save} disabled={!can("member") || !c.name || !c.slug}>Save contract</button>
          {!isNew && can("member") && <button onClick={async () => { if (window.confirm(`Delete contract "${c.name}"?`)) { await api(`/api/llm/contracts/${initial.id}`, { method: "DELETE" }); onDeleted(); } }}>Delete</button>}
          {msg && <span className={msg.ok ? "small" : "small"} style={{ color: msg.ok ? "var(--good-text)" : "var(--critical-text)" }}>{msg.text}</span>}
        </div>
      </Card>

      <Card title="Try it" sub="Run these rules against a sample exchange. Nothing is stored.">
        <div className="form-grid">
          <label className="field">System prompt<textarea value={test.system} onChange={(e) => setTest({ ...test, system: e.target.value })} /></label>
          <label className="field">User message<textarea value={test.user} onChange={(e) => setTest({ ...test, user: e.target.value })} /></label>
          <label className="field wide">Model response<textarea value={test.response} onChange={(e) => setTest({ ...test, response: e.target.value })} style={{ minHeight: 90 }} /></label>
          <label className="check-row"><input type="checkbox" checked={test.use_judge} onChange={(e) => setTest({ ...test, use_judge: e.target.checked })} /> Run judge rules (uses your judge key)</label>
        </div>
        <button style={{ marginTop: 10 }} onClick={runTest} disabled={!test.response}>Run checks</button>
        {testResult?.error && <div className="error-box small" style={{ marginTop: 10 }}>{testResult.error}</div>}
        {testResult?.checks && (
          <div style={{ marginTop: 12 }}>
            <div className="small" style={{ marginBottom: 6 }}>
              {testResult.would_block ? <span className="badge critical">✕ Would be blocked / repaired</span> : <span className="badge healthy">✓ Would pass</span>}
              {testResult.adherence != null && <span className="text-2"> · adherence {fmtPct(testResult.adherence)}</span>}
            </div>
            <table>
              <tbody>
                {testResult.checks.map((x, i) => (
                  <tr key={i}><td className="small">{x.label}</td>
                    <td>{x.skipped ? <span className="badge neutral">Skipped</span> : x.passed ? <span className="badge healthy">✓</span> : <span className={`badge ${x.severity === "critical" ? "critical" : "warning"}`}>✕</span>}</td>
                    <td className="small text-2">{x.detail}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
