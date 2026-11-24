import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { api, useApi } from "../../api";
import { useAuth } from "../../auth";
import { Async, Card } from "../../components/ui";
import { fmtAgo, fmtInt, fmtTime, fmtUsd } from "../../format";

const BLANK = { name: "", system_prompt: "", template: "", model: "", labels: "", commit_message: "" };

export default function Prompts() {
  const [params, setParams] = useSearchParams();
  const list = useApi("/api/llm/prompts");
  const { can } = useAuth();
  const [draft, setDraft] = useState(null);
  const selected = params.get("name");

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Prompts</h1>
          <p>Version your prompts here instead of in code. Apps fetch the version labeled <code>production</code> (or any label),
            and every call sent with <code>X-AOBS-Prompt: name@version</code> is counted against that version.</p>
        </div>
        {can("member") && <button className="primary" onClick={() => setDraft(BLANK)}>New prompt</button>}
      </div>
      {draft && <PromptForm initial={draft} onClose={() => setDraft(null)}
                            onSaved={(p) => { setDraft(null); list.reload(); setParams({ name: p.name }); }} />}
      <Card flush style={{ marginBottom: 16 }}>
        <Async state={list}>
          {(rows) => rows.length === 0 ? <div className="empty">No prompts yet.</div> : (
            <table>
              <thead><tr><th>Prompt</th><th className="r">Versions</th><th>Labels</th><th>Updated</th></tr></thead>
              <tbody>
                {rows.map((p) => (
                  <tr key={p.name} className="clickable" onClick={() => setParams({ name: p.name })} style={p.name === selected ? { fontWeight: 600 } : undefined}>
                    <td className="mono">{p.name}<div className="small muted">{p.model}</div></td>
                    <td className="r">{p.versions}</td>
                    <td className="small">{Object.entries(p.labels).map(([l, v]) => <span key={l} className="badge neutral" style={{ marginRight: 4 }}>{l} → v{v}</span>)}</td>
                    <td className="small">{fmtAgo(p.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Async>
      </Card>
      {selected && <Versions name={selected} onNew={(v) => setDraft({ ...BLANK, ...v, labels: "", commit_message: "" })} onChange={list.reload} />}
    </>
  );
}

function Versions({ name, onNew, onChange }) {
  const state = useApi(`/api/llm/prompts/${encodeURIComponent(name)}`);
  const { can } = useAuth();
  const setLabels = async (version, labels) => {
    try {
      await api(`/api/llm/prompts/${encodeURIComponent(name)}/versions/${version}/labels`, { method: "PUT", body: { labels } });
      state.reload(); onChange();
    } catch (e) { toast.error(e.message); }
  };
  return (
    <Async state={state}>
      {(d) => (
        <Card title={`${d.name}: versions`} flush
              right={can("member") && <button onClick={() => onNew({ name: d.name, system_prompt: d.versions[0].system_prompt, template: d.versions[0].template, model: d.versions[0].model })}>New version</button>}>
          <table>
            <thead><tr><th>Version</th><th>Prompt</th><th>Labels</th><th className="r">Calls</th><th className="r">Critical</th><th className="r">Cost</th><th></th></tr></thead>
            <tbody>
              {d.versions.map((v) => {
                const own = v.labels.filter((l) => l !== "latest");
                return (
                  <tr key={v.version}>
                    <td>v{v.version}<div className="small muted">{fmtTime(v.created_at)}<br />{v.created_by}</div></td>
                    <td style={{ maxWidth: 420 }}>
                      {v.commit_message && <div className="small">{v.commit_message}</div>}
                      {v.system_prompt && <div className="small muted truncate" title={v.system_prompt}>System: {v.system_prompt}</div>}
                      <pre className="output">{v.template || "–"}</pre>
                    </td>
                    <td className="small">{v.labels.map((l) => <span key={l} className={`badge ${l === "production" ? "healthy" : "neutral"}`} style={{ marginRight: 4 }}>{l}</span>)}</td>
                    <td className="r small">{fmtInt(v.usage?.calls || 0)}</td>
                    <td className="r small">{fmtInt(v.usage?.critical || 0)}</td>
                    <td className="r small">{fmtUsd(v.usage?.cost_usd || 0, 4)}</td>
                    <td className="r" style={{ whiteSpace: "nowrap" }}>
                      {can("member") && !own.includes("production") && <button onClick={() => setLabels(v.version, [...own, "production"])}>Promote to production</button>}
                      {can("member") && own.length > 0 && <button onClick={() => setLabels(v.version, [])} style={{ marginLeft: 4 }}>Clear labels</button>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>
      )}
    </Async>
  );
}

function PromptForm({ initial, onClose, onSaved }) {
  const [p, setP] = useState(initial);
  const [err, setErr] = useState(null);
  const set = (k, v) => setP({ ...p, [k]: v });
  const save = async () => {
    setErr(null);
    try {
      onSaved(await api("/api/llm/prompts", { method: "POST", body: {
        name: p.name, system_prompt: p.system_prompt, template: p.template, model: p.model, commit_message: p.commit_message,
        labels: p.labels.split(",").map((x) => x.trim()).filter(Boolean),
      } }));
      toast.success("Version saved");
    } catch (e) { setErr(e.message); }
  };
  return (
    <Card title={initial.name ? `New version of “${initial.name}”` : "New prompt"} style={{ marginBottom: 16 }}>
      <div className="form-grid">
        <label className="field">Name<input type="text" value={p.name} disabled={!!initial.name} onChange={(e) => set("name", e.target.value)} placeholder="support-reply" /></label>
        <label className="field">Model (optional)<input type="text" value={p.model} onChange={(e) => set("model", e.target.value)} placeholder="gpt-4o-mini" /></label>
        <label className="field wide">System prompt<textarea value={p.system_prompt} onChange={(e) => set("system_prompt", e.target.value)} /></label>
        <label className="field wide">User message template<textarea value={p.template} onChange={(e) => set("template", e.target.value)} placeholder="Reply to this customer: {{input}}" /></label>
        <label className="field">Labels (comma-separated)<input type="text" value={p.labels} onChange={(e) => set("labels", e.target.value)} placeholder="production, staging" /></label>
        <label className="field">What changed<input type="text" value={p.commit_message} onChange={(e) => set("commit_message", e.target.value)} /></label>
      </div>
      <div className="small muted" style={{ marginTop: 8 }}>Use <code>{"{{name}}"}</code> placeholders; the SDK fills them with <code>prompt.compile(name=...)</code>. Experiments fill <code>{"{{input}}"}</code> from each dataset item. Versions can't be edited once saved.</div>
      {err && <div className="error-box small" style={{ marginTop: 10 }}>{err}</div>}
      <div className="row" style={{ marginTop: 12 }}>
        <button className="primary" onClick={save} disabled={!p.name}>Save version</button>
        <button onClick={onClose}>Cancel</button>
      </div>
    </Card>
  );
}
