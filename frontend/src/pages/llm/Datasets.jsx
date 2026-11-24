import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { api, useApi } from "../../api";
import { useAuth } from "../../auth";
import { Async, Card, useConfirm } from "../../components/ui";
import { fmtAgo, fmtInt, fmtNum, fmtPct, fmtUsd } from "../../format";
import { PROVIDER_LABEL } from "./common";

const STATUS = { running: ["info", "Running…"], done: ["healthy", "Done"], error: ["critical", "Error"] };

export default function Datasets() {
  const [params, setParams] = useSearchParams();
  const list = useApi("/api/llm/datasets", { refreshMs: 10000 });
  const { can } = useAuth();
  const [name, setName] = useState("");
  const selected = params.get("id");
  const create = async () => {
    try {
      const d = await api("/api/llm/datasets", { method: "POST", body: { name } });
      setName(""); list.reload(); setParams({ id: d.id });
    } catch (e) { toast.error(e.message); }
  };

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Datasets & experiments</h1>
          <p>Collect test cases (write them, or use “Add to dataset” on any real call), then run them against a model and prompt version.
            Each answer is scored by your checks and a contract, so you can compare versions before you ship one.</p>
        </div>
        {can("member") && (
          <div className="row">
            <input type="text" placeholder="New dataset name" value={name} onChange={(e) => setName(e.target.value)} onKeyDown={(e) => e.key === "Enter" && name && create()} />
            <button className="primary" disabled={!name} onClick={create}>Create</button>
          </div>
        )}
      </div>
      <Card flush style={{ marginBottom: 16 }}>
        <Async state={list}>
          {(rows) => rows.length === 0 ? <div className="empty">No datasets yet.</div> : (
            <table>
              <thead><tr><th>Dataset</th><th className="r">Items</th><th>Last experiment</th><th className="r">Pass rate</th></tr></thead>
              <tbody>
                {rows.map((d) => (
                  <tr key={d.id} className="clickable" onClick={() => setParams({ id: d.id })} style={String(d.id) === selected ? { fontWeight: 600 } : undefined}>
                    <td>{d.name}<div className="small muted">{d.description}</div></td>
                    <td className="r">{fmtInt(d.items)}</td>
                    <td className="small">{d.last_experiment ? <>{d.last_experiment.name} · {d.last_experiment.model} · {fmtAgo(d.last_experiment.created_at)}</> : "–"}</td>
                    <td className="r small">{fmtPct(d.last_experiment?.summary?.pass_rate)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Async>
      </Card>
      {selected && <DatasetBody id={selected} onChange={list.reload} exp={params.get("exp")}
                                onExp={(e) => setParams(e ? { id: selected, exp: e } : { id: selected })} />}
    </>
  );
}

function DatasetBody({ id, onChange, exp, onExp }) {
  const { can } = useAuth();
  const confirm = useConfirm();
  const state = useApi(`/api/llm/datasets/${id}`, { refreshMs: 5000 });
  const [item, setItem] = useState({ input: "", expected: "" });
  const reload = () => { state.reload(); onChange(); };
  const addItem = async () => {
    try { await api(`/api/llm/datasets/${id}/items`, { method: "POST", body: item }); setItem({ input: "", expected: "" }); reload(); }
    catch (e) { toast.error(e.message); }
  };
  return (
    <Async state={state}>
      {(d) => (
        <>
          <div className="grid cols-2" style={{ marginBottom: 16 }}>
            <Card title={`${d.name}: items`} flush sub={`${d.items.length} test cases`}
                  right={can("member") && <button onClick={async () => { if (await confirm({ title: `Delete dataset “${d.name}”?`, body: "Its items, experiments and results are deleted too. This cannot be undone.", confirmLabel: "Delete", danger: true })) { await api(`/api/llm/datasets/${id}`, { method: "DELETE" }); onChange(); onExp(null); } }}>Delete dataset</button>}>
              {can("member") && (
                <div className="form-grid" style={{ padding: 12 }}>
                  <label className="field wide">Input<textarea value={item.input} onChange={(e) => setItem({ ...item, input: e.target.value })} placeholder="A request your app receives" /></label>
                  <label className="field wide">Expected answer (optional)<textarea value={item.expected} onChange={(e) => setItem({ ...item, expected: e.target.value })} /></label>
                  <div><button disabled={!item.input} onClick={addItem}>Add item</button></div>
                </div>
              )}
              {d.items.length === 0 ? <div className="empty">No items yet.</div> : (
                <table>
                  <thead><tr><th>Input</th><th>Expected</th><th></th></tr></thead>
                  <tbody>
                    {d.items.map((i) => (
                      <tr key={i.id}>
                        <td className="small" style={{ maxWidth: 260 }}><div className="truncate" title={i.input}>{i.input}</div>
                          {i.source_call_id && <Link className="muted" to={`/llm/calls/${i.source_call_id}`}>from a real call</Link>}</td>
                        <td className="small text-2" style={{ maxWidth: 220 }}><div className="truncate" title={i.expected}>{i.expected || "–"}</div></td>
                        <td className="r">{can("member") && <button onClick={async () => { await api(`/api/llm/datasets/${id}/items/${i.id}`, { method: "DELETE" }); reload(); }}>Remove</button>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Card>
            <div className="stack">
              {can("member") && d.items.length > 0 && <RunForm datasetId={id} onStarted={(e) => { reload(); onExp(e.id); }} />}
              <Card title="Experiments" flush sub="Compare runs side by side">
                {d.experiments.length === 0 ? <div className="empty">No experiments yet.</div> : (
                  <table>
                    <thead><tr><th>Experiment</th><th>Status</th><th className="r">Pass rate</th><th className="r">Similarity</th><th className="r">Cost</th></tr></thead>
                    <tbody>
                      {d.experiments.map((e) => {
                        const [cls, label] = STATUS[e.status] || STATUS.error;
                        return (
                          <tr key={e.id} className="clickable" onClick={() => onExp(e.id)} style={String(e.id) === exp ? { fontWeight: 600 } : undefined}>
                            <td className="small">{e.name}<div className="muted">{e.model}{e.prompt_name ? ` · ${e.prompt_name} v${e.prompt_version}` : ""}</div></td>
                            <td><span className={`badge ${cls}`}>{label}</span></td>
                            <td className="r small">{fmtPct(e.summary?.pass_rate)}</td>
                            <td className="r small">{fmtNum(e.summary?.avg_similarity)}</td>
                            <td className="r small">{fmtUsd(e.summary?.cost_usd, 4)}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                )}
              </Card>
            </div>
          </div>
          {exp && <Results id={exp} />}
        </>
      )}
    </Async>
  );
}

function RunForm({ datasetId, onStarted }) {
  const creds = useApi("/api/workspace/credentials");
  const contracts = useApi("/api/llm/contracts");
  const prompts = useApi("/api/llm/prompts");
  const [f, setF] = useState({ name: "", provider: "openai", model: "gpt-4o-mini", credential_id: "", prompt_name: "", prompt_version: "", contract_id: "" });
  const set = (k, v) => setF({ ...f, [k]: v });
  const prompt = (prompts.data || []).find((p) => p.name === f.prompt_name);
  const start = async () => {
    try {
      onStarted(await api(`/api/llm/datasets/${datasetId}/experiments`, { method: "POST", body: {
        name: f.name || `${f.model}${f.prompt_name ? ` · ${f.prompt_name}` : ""}`, provider: f.provider, model: f.model,
        credential_id: f.credential_id ? Number(f.credential_id) : null, prompt_name: f.prompt_name,
        prompt_version: f.prompt_version ? Number(f.prompt_version) : null, contract_id: f.contract_id ? Number(f.contract_id) : null,
      } }));
      toast.success("Experiment started");
    } catch (e) { toast.error(e.message); }
  };
  return (
    <Card title="Run an experiment">
      <div className="form-grid">
        <label className="field">Name<input type="text" value={f.name} onChange={(e) => set("name", e.target.value)} placeholder="e.g. v2 prompt on mini" /></label>
        <label className="field">Provider
          <select value={f.provider} onChange={(e) => setF({ ...f, provider: e.target.value, credential_id: "" })}>
            {Object.entries(PROVIDER_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
        <label className="field">Model<input type="text" value={f.model} onChange={(e) => set("model", e.target.value)} /></label>
        <label className="field">Provider key
          <select value={f.credential_id} onChange={(e) => set("credential_id", e.target.value)}>
            <option value="">Default for provider</option>
            {(creds.data || []).filter((c) => c.provider === f.provider).map((c) => <option key={c.id} value={c.id}>{c.name} ({c.key_hint})</option>)}
          </select>
        </label>
        <label className="field">Prompt (optional)
          <select value={f.prompt_name} onChange={(e) => setF({ ...f, prompt_name: e.target.value, prompt_version: "" })}>
            <option value="">None: send each item as-is</option>
            {(prompts.data || []).map((p) => <option key={p.name} value={p.name}>{p.name}</option>)}
          </select>
        </label>
        {prompt && (
          <label className="field">Version
            <select value={f.prompt_version} onChange={(e) => set("prompt_version", e.target.value)}>
              <option value="">Latest (v{prompt.latest_version})</option>
              {Array.from({ length: prompt.latest_version }, (_, i) => prompt.latest_version - i).map((v) => <option key={v} value={v}>v{v}</option>)}
            </select>
          </label>
        )}
        <label className="field">Score with contract
          <select value={f.contract_id} onChange={(e) => set("contract_id", e.target.value)}>
            <option value="">Built-in checks only</option>
            {(contracts.data || []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </label>
      </div>
      <div className="small muted" style={{ marginTop: 8 }}>Runs up to 200 items. Each item is a real (billed) call with your provider key.</div>
      <div className="row" style={{ marginTop: 12 }}><button className="primary" disabled={!f.model} onClick={start}>Run</button></div>
    </Card>
  );
}

function Results({ id }) {
  const state = useApi(`/api/llm/experiments/${id}`, { refreshMs: 3000 });
  return (
    <Async state={state}>
      {(e) => (
        <Card title={`Results: ${e.name}`} flush
              sub={e.status === "error" ? e.detail : `${e.summary?.passed ?? 0} of ${e.summary?.items ?? e.results.length} passed${e.summary?.errors ? ` · ${e.summary.errors} errors` : ""}${e.summary?.avg_latency_ms ? ` · avg ${fmtInt(e.summary.avg_latency_ms)} ms` : ""}`}>
          {e.results.length === 0 ? <div className="empty">{e.status === "running" ? "Running…" : "No results."}</div> : (
            <table>
              <thead><tr><th>Input</th><th>Answer</th><th>Result</th><th className="r">Similarity</th><th className="r">Latency</th></tr></thead>
              <tbody>
                {e.results.map((r) => (
                  <tr key={r.id}>
                    <td className="small" style={{ maxWidth: 240 }}><div className="truncate" title={r.input}>{r.input}</div></td>
                    <td style={{ maxWidth: 420 }}><pre className="output">{r.status === "error" ? r.detail : r.output}</pre>
                      {r.call_id && <Link className="small" to={`/llm/calls/${r.call_id}`}>Call details</Link>}</td>
                    <td>{r.status === "error" ? <span className="badge warning">Error</span> : r.passed ? <span className="badge healthy">✓ Pass</span>
                      : <span className="badge critical" title={r.detail}>✕ Fail</span>}
                      {!r.passed && r.detail && r.status !== "error" && <div className="small muted">{r.detail}</div>}</td>
                    <td className="r small">{fmtNum(r.similarity)}</td>
                    <td className="r small">{fmtInt(r.latency_ms)} ms</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      )}
    </Async>
  );
}
