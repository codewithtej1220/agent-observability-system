import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, useApi } from "../api";
import { useAuth } from "../auth";
import { Async, Card } from "../components/ui";
import { fmtAgo } from "../format";

const TABS = [
  ["workspace", "Workspace"], ["members", "Members"], ["api-keys", "API keys"], ["providers", "Provider keys"],
  ["privacy", "Privacy & judge"], ["account", "Account"],
];
const PROVIDER_LABEL = { openai: "OpenAI", anthropic: "Anthropic (Claude)", gemini: "Google Gemini" };

function useAction() {
  const [msg, setMsg] = useState(null);
  const run = async (fn, ok) => {
    setMsg(null);
    try {
      const r = await fn();
      if (ok) setMsg({ ok: true, text: typeof ok === "function" ? ok(r) : ok });
      return r;
    } catch (e) {
      setMsg({ ok: false, text: e.message });
      return null;
    }
  };
  const view = msg && <div className={msg.ok ? "note small" : "error-box small"} style={{ marginTop: 10 }}>{msg.text}</div>;
  return [run, view];
}

export default function Settings() {
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") || "workspace";
  return (
    <>
      <div className="page-head"><div><h1>Settings</h1></div></div>
      <div className="tabs">
        {TABS.map(([id, label]) => (
          <button key={id} className={tab === id ? "on" : ""} onClick={() => setParams({ tab: id })}>{label}</button>
        ))}
      </div>
      {tab === "workspace" && <WorkspaceTab />}
      {tab === "members" && <MembersTab />}
      {tab === "api-keys" && <ApiKeysTab />}
      {tab === "providers" && <ProvidersTab />}
      {tab === "privacy" && <PrivacyTab />}
      {tab === "account" && <AccountTab />}
    </>
  );
}

function WorkspaceTab() {
  const { workspace, can, refresh } = useAuth();
  const [name, setName] = useState(workspace.name);
  const [newName, setNewName] = useState("");
  const [run, view] = useAction();
  return (
    <div className="grid cols-2">
      <Card title="This workspace" sub="Everything you see is scoped to the current workspace.">
        <label className="field">Name
          <input type="text" value={name} onChange={(e) => setName(e.target.value)} disabled={!can("admin")} />
        </label>
        {can("admin") && (
          <button style={{ marginTop: 10 }} onClick={() => run(async () => { await api("/api/workspace", { method: "PATCH", body: { name } }); await refresh(); }, "Saved")}>Save</button>
        )}
        {view}
      </Card>
      <Card title="Create another workspace" sub="Separate data, members and keys, e.g. per team or environment.">
        <label className="field">Name<input type="text" value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="e.g. Production" /></label>
        <button style={{ marginTop: 10 }} disabled={!newName.trim()}
                onClick={() => run(async () => { await api("/api/workspaces", { method: "POST", body: { name: newName } }); window.location.assign("/settings"); })}>
          Create and switch
        </button>
      </Card>
    </div>
  );
}

function MembersTab() {
  const { can, user } = useAuth();
  const members = useApi("/api/workspace/members");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("member");
  const [run, view] = useAction();
  const act = (fn) => run(async () => { await fn(); members.reload(); });
  return (
    <div className="grid cols-3">
      <Card title="Members" className="span-2" flush>
        <Async state={members}>
          {(rows) => (
            <table>
              <thead><tr><th>Member</th><th>Role</th><th>Last sign-in</th><th></th></tr></thead>
              <tbody>
                {rows.map((m) => (
                  <tr key={m.user_id}>
                    <td>{m.name || m.email}<div className="small muted">{m.email}</div></td>
                    <td>
                      {can("admin") ? (
                        <select value={m.role} onChange={(e) => act(() => api(`/api/workspace/members/${m.user_id}`, { method: "PATCH", body: { role: e.target.value } }))}>
                          <option value="admin">Admin</option><option value="member">Member</option><option value="viewer">Viewer</option>
                        </select>
                      ) : m.role}
                    </td>
                    <td className="small">{fmtAgo(m.last_login_at)}</td>
                    <td className="r">{can("admin") && m.user_id !== user.id && (
                      <button onClick={() => act(() => api(`/api/workspace/members/${m.user_id}`, { method: "DELETE" }))}>Remove</button>)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Async>
        <div style={{ padding: "0 16px 12px" }}>{view}</div>
      </Card>
      <Card title="Add a member" sub="They need an account first (sign-up or Google).">
        <div className="stack" style={{ gap: 10 }}>
          <label className="field">Email<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} disabled={!can("admin")} /></label>
          <label className="field">Role
            <select value={role} onChange={(e) => setRole(e.target.value)} disabled={!can("admin")}>
              <option value="viewer">Viewer — read only</option>
              <option value="member">Member — configure monitoring, create API keys</option>
              <option value="admin">Admin — members, provider keys, settings</option>
            </select>
          </label>
          <button className="primary" disabled={!can("admin") || !email}
                  onClick={() => act(async () => { await api("/api/workspace/members", { method: "POST", body: { email, role } }); setEmail(""); })}>Add member</button>
          {!can("admin") && <div className="small muted">Only admins can manage members.</div>}
        </div>
      </Card>
    </div>
  );
}

function ApiKeysTab() {
  const { can } = useAuth();
  const keys = useApi("/api/workspace/api-keys");
  const [name, setName] = useState("");
  const [created, setCreated] = useState(null);
  const [run, view] = useAction();
  return (
    <div className="grid cols-3">
      <Card title="API keys" className="span-2" flush sub="Used by your apps for the LLM gateway and the agent SDK. Keys are stored hashed.">
        <Async state={keys}>
          {(rows) => rows.length === 0 ? <div className="empty">No API keys yet.</div> : (
            <table>
              <thead><tr><th>Name</th><th>Key</th><th>Created</th><th>Last used</th><th></th></tr></thead>
              <tbody>
                {rows.map((k) => (
                  <tr key={k.id} style={k.revoked ? { opacity: 0.55 } : undefined}>
                    <td>{k.name}</td><td className="mono">{k.prefix}…</td>
                    <td className="small">{fmtAgo(k.created_at)}</td><td className="small">{k.last_used_at ? fmtAgo(k.last_used_at) : "Never"}</td>
                    <td className="r">{k.revoked ? <span className="badge neutral">Revoked</span> : can("member") && (
                      <button onClick={() => run(async () => { await api(`/api/workspace/api-keys/${k.id}`, { method: "DELETE" }); keys.reload(); })}>Revoke</button>)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Async>
        <div style={{ padding: "0 16px 12px" }}>{view}</div>
      </Card>
      <Card title="Create a key">
        <div className="stack" style={{ gap: 10 }}>
          <label className="field">Name<input type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. support-bot production" /></label>
          <button className="primary" disabled={!name.trim() || !can("member")}
                  onClick={() => run(async () => { const r = await api("/api/workspace/api-keys", { method: "POST", body: { name } }); setCreated(r); setName(""); keys.reload(); })}>
            Create key
          </button>
          {created && (
            <div>
              <div className="small" style={{ marginBottom: 6 }}><strong>Copy this key now.</strong> It will not be shown again.</div>
              <div className="secret">{created.key}</div>
              <button style={{ marginTop: 8 }} onClick={() => navigator.clipboard?.writeText(created.key)}>Copy</button>
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}

function ProvidersTab() {
  const { can } = useAuth();
  const creds = useApi("/api/workspace/credentials");
  const [form, setForm] = useState({ provider: "openai", name: "default", api_key: "" });
  const [tests, setTests] = useState({});
  const [run, view] = useAction();
  const test = async (id) => {
    setTests((t) => ({ ...t, [id]: { text: "Testing…" } }));
    try {
      const r = await api(`/api/workspace/credentials/${id}/test`, { method: "POST" });
      setTests((t) => ({ ...t, [id]: { ok: r.ok, text: r.message } }));
    } catch (e) {
      setTests((t) => ({ ...t, [id]: { ok: false, text: e.message } }));
    }
  };
  return (
    <div className="grid cols-3">
      <Card title="Provider keys" className="span-2" flush
            sub="Encrypted at rest (AES with HMAC). The plaintext key is never shown again or sent to the browser.">
        <Async state={creds}>
          {(rows) => rows.length === 0 ? <div className="empty">No provider keys yet. Add one to start routing calls through the gateway.</div> : (
            <table>
              <thead><tr><th>Provider</th><th>Name</th><th>Key</th><th>Last used</th><th></th></tr></thead>
              <tbody>
                {rows.map((c) => (
                  <tr key={c.id}>
                    <td>{PROVIDER_LABEL[c.provider]}{c.is_default && <span className="badge neutral" style={{ marginLeft: 6 }}>Default</span>}</td>
                    <td>{c.name}</td><td className="mono">{c.key_hint}</td>
                    <td className="small">{c.last_used_at ? fmtAgo(c.last_used_at) : "Never"}</td>
                    <td className="r" style={{ whiteSpace: "nowrap" }}>
                      {tests[c.id] && <span className={`small ${tests[c.id].ok ? "" : "text-2"}`} style={{ marginRight: 8, color: tests[c.id].ok ? "var(--good-text)" : undefined }}>{tests[c.id].text}</span>}
                      {can("admin") && <>
                        <button onClick={() => test(c.id)}>Test</button>{" "}
                        <button onClick={() => run(async () => { await api(`/api/workspace/credentials/${c.id}`, { method: "DELETE" }); creds.reload(); })}>Delete</button>
                      </>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Async>
        <div style={{ padding: "0 16px 12px" }}>{view}</div>
      </Card>
      <Card title="Add a provider key" sub={can("admin") ? "Saving a key with an existing name replaces it." : "Only admins can manage provider keys."}>
        <div className="stack" style={{ gap: 10 }}>
          <label className="field">Provider
            <select value={form.provider} onChange={(e) => setForm({ ...form, provider: e.target.value })} disabled={!can("admin")}>
              {Object.entries(PROVIDER_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
          <label className="field">Name<input type="text" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} disabled={!can("admin")} /></label>
          <label className="field">API key
            <input type="password" autoComplete="off" value={form.api_key} onChange={(e) => setForm({ ...form, api_key: e.target.value })} disabled={!can("admin")} />
          </label>
          <button className="primary" disabled={!can("admin") || form.api_key.length < 8}
                  onClick={() => run(async () => { await api("/api/workspace/credentials", { method: "POST", body: { ...form, is_default: true } }); setForm({ ...form, api_key: "" }); creds.reload(); }, "Saved and encrypted")}>
            Save key
          </button>
        </div>
      </Card>
    </div>
  );
}

function PrivacyTab() {
  const { can } = useAuth();
  const ws = useApi("/api/workspace");
  const creds = useApi("/api/workspace/credentials");
  return <Async state={ws}>{(d) => <PrivacyForm d={d} creds={creds.data || []} admin={can("admin")} reload={ws.reload} />}</Async>;
}

function PrivacyForm({ d, creds, admin, reload }) {
  const [s, setS] = useState(d.settings);
  const [run, view] = useAction();
  const set = (k, v) => setS({ ...s, [k]: v });
  const save = () => run(async () => {
    await api("/api/workspace", { method: "PATCH", body: {
      store_content: s.store_content, redact_pii: s.redact_pii, retention_days: Number(s.retention_days),
      auto_judge: s.auto_judge, judge_sample_rate: Number(s.judge_sample_rate),
      judge_credential_id: s.judge_credential_id ? Number(s.judge_credential_id) : null, judge_model: s.judge_model || null,
    } });
    reload();
  }, "Saved");
  return (
    <div className="grid cols-2">
      <Card title="Stored content" sub="What the gateway keeps about each LLM call.">
        <div className="stack" style={{ gap: 12 }}>
          <label className="check-row"><input type="checkbox" checked={s.store_content} disabled={!admin} onChange={(e) => set("store_content", e.target.checked)} />
            Store prompts and responses (metrics and check results are always kept)</label>
          <label className="check-row"><input type="checkbox" checked={s.redact_pii} disabled={!admin} onChange={(e) => set("redact_pii", e.target.checked)} />
            Mask emails, phone numbers, card numbers and SSNs before storing</label>
          <label className="field">Delete stored content after (days)
            <input type="number" min={1} max={3650} value={s.retention_days} disabled={!admin} onChange={(e) => set("retention_days", e.target.value)} style={{ maxWidth: 140 }} />
          </label>
        </div>
      </Card>
      <Card title="LLM judge" sub="Evaluates rules that need understanding (tone, scope, faithfulness). Uses one of your provider keys.">
        <div className="stack" style={{ gap: 12 }}>
          <label className="field">Judge key
            <select value={s.judge_credential_id || ""} disabled={!admin} onChange={(e) => set("judge_credential_id", e.target.value)}>
              <option value="">Not configured</option>
              {creds.map((c) => <option key={c.id} value={c.id}>{PROVIDER_LABEL[c.provider]} · {c.name}</option>)}
            </select>
          </label>
          <label className="field">Judge model
            <input type="text" value={s.judge_model || ""} disabled={!admin} onChange={(e) => set("judge_model", e.target.value)}
                   placeholder="Default: gpt-4o-mini / claude-haiku-4-5 / gemini-3.5-flash" />
          </label>
          <label className="check-row"><input type="checkbox" checked={s.auto_judge} disabled={!admin} onChange={(e) => set("auto_judge", e.target.checked)} />
            Also judge calls without a contract against their own system prompt</label>
          <label className="field">Share of those calls to judge (cost control)
            <input type="number" step="0.05" min={0} max={1} value={s.judge_sample_rate} disabled={!admin || !s.auto_judge}
                   onChange={(e) => set("judge_sample_rate", e.target.value)} style={{ maxWidth: 140 }} />
          </label>
          <div className="small muted">Tip: judge with a different provider than the one being monitored, so a model does not grade its own answers.</div>
        </div>
      </Card>
      {admin && <div><button className="primary" onClick={save}>Save settings</button>{view}</div>}
    </div>
  );
}

function AccountTab() {
  const { user } = useAuth();
  const [form, setForm] = useState({ current_password: "", new_password: "" });
  const [run, view] = useAction();
  return (
    <div className="grid cols-2">
      <Card title="Profile">
        <dl className="kv">
          <dt>Name</dt><dd>{user.name || "–"}</dd>
          <dt>Email</dt><dd>{user.email}</dd>
          <dt>Google</dt><dd>{user.google_linked ? "Linked" : "Not linked"}</dd>
        </dl>
      </Card>
      <Card title={user.has_password ? "Change password" : "Set a password"} sub="Other signed-in sessions will be signed out.">
        <div className="stack" style={{ gap: 10 }}>
          {user.has_password && (
            <label className="field">Current password
              <input type="password" autoComplete="current-password" value={form.current_password} onChange={(e) => setForm({ ...form, current_password: e.target.value })} />
            </label>
          )}
          <label className="field">New password
            <input type="password" autoComplete="new-password" value={form.new_password} onChange={(e) => setForm({ ...form, new_password: e.target.value })} />
          </label>
          <button className="primary" disabled={form.new_password.length < 8}
                  onClick={() => run(async () => { await api("/api/auth/password", { method: "POST", body: form }); setForm({ current_password: "", new_password: "" }); }, "Password updated")}>
            Save password
          </button>
          {view}
        </div>
      </Card>
    </div>
  );
}
