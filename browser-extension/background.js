// Agent Observability chat monitor: background service worker.
// Receives finished turns from the content script and forwards them to the API.
// Runs here (not in the page) so requests are not subject to the chat site's CORS rules.

const DEFAULTS = { apiUrl: "http://127.0.0.1:8000", apiKey: "", project: "", paused: false, sites: {} };

async function config() {
  return chrome.storage.local.get(DEFAULTS);
}

async function record(update) {
  const s = await chrome.storage.local.get({ stats: { sent: 0, issues: 0, recent: [] } });
  const stats = s.stats;
  if (update.ok) {
    stats.sent += 1;
    if (update.severity && update.severity !== "ok") stats.issues += 1;
    stats.recent = [{ at: Date.now(), app: update.app, severity: update.severity, failed: update.failed, url: update.url }, ...stats.recent].slice(0, 8);
    stats.lastError = null;
  } else {
    stats.lastError = { at: Date.now(), message: update.error };
  }
  await chrome.storage.local.set({ stats });
}

async function sendTurn(payload) {
  const cfg = await config();
  if (cfg.paused || cfg.sites[payload.app] === false) return { skipped: true };
  if (!cfg.apiKey) {
    const error = "Set your workspace API key in the extension options";
    await record({ ok: false, error });
    return { error };
  }
  try {
    const res = await fetch(`${cfg.apiUrl.replace(/\/$/, "")}/api/llm/ingest/browser-turn`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-API-Key": cfg.apiKey },
      body: JSON.stringify({ ...payload, project: cfg.project || null }),
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      const error = res.status === 401 ? "API key rejected" : `HTTP ${res.status}: ${typeof body.detail === "string" ? body.detail : ""}`;
      await record({ ok: false, error });
      return { error };
    }
    await record({ ok: true, app: payload.app, ...body });
    return body;
  } catch (e) {
    const error = `Cannot reach ${cfg.apiUrl} (is the API running?)`;
    await record({ ok: false, error });
    return { error };
  }
}

async function testConnection() {
  const cfg = await config();
  if (!cfg.apiKey) return { ok: false, message: "No API key set" };
  try {
    const res = await fetch(`${cfg.apiUrl.replace(/\/$/, "")}/api/llm/connect`, { headers: { "X-API-Key": cfg.apiKey } });
    if (res.status === 401) return { ok: false, message: "API key rejected (revoked or mistyped?)" };
    if (!res.ok) return { ok: false, message: `HTTP ${res.status}` };
    return { ok: true, message: "Connected" };
  } catch {
    return { ok: false, message: `Cannot reach ${cfg.apiUrl}` };
  }
}

chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
  if (msg?.type === "turn") { sendTurn(msg.payload).then(reply); return true; }
  if (msg?.type === "test") { testConnection().then(reply); return true; }
  return false;
});
