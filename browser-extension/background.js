// Agent Observability chat monitor: background service worker.
// Receives finished turns from the content script and forwards them to the API.
// Runs here (not in the page) so requests are not subject to the chat site's CORS rules.
// If the local API is not running, asks the native helper (native-host/) to start it.

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

const HOST = "com.aobs.launcher";
let lastEnsure = 0;

async function apiUp(cfg) {
  try {
    const res = await fetch(`${cfg.apiUrl.replace(/\/$/, "")}/health`, { signal: AbortSignal.timeout(1500) });
    return res.ok;
  } catch {
    return false;
  }
}

// Start the API and dashboard through the native helper if they are not running (throttled).
async function ensureServers() {
  const cfg = await config();
  if (await apiUp(cfg)) return { ok: true, api: "running" };
  if (Date.now() - lastEnsure < 15000) return { ok: true, api: "starting" };
  lastEnsure = Date.now();
  try {
    const r = await chrome.runtime.sendNativeMessage(HOST, { cmd: "ensure" });
    await chrome.storage.local.set({ helper: { ok: !!r?.ok, at: Date.now(), error: r?.error || null } });
    return r;
  } catch (e) {
    const error = `Auto-start helper not installed (${e.message || e}). Run browser-extension/native-host/install.py`;
    await chrome.storage.local.set({ helper: { ok: false, at: Date.now(), error } });
    return { ok: false, error };
  }
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
      const detail = typeof body.detail === "string" ? body.detail : "";
      const error = res.status === 401 ? "API key rejected"
        : res.status === 402 ? `Plan limit: ${detail}`
        : res.status === 429 ? "Rate limited; this turn was not tracked"
        : `HTTP ${res.status}: ${detail}`;
      await record({ ok: false, error });
      return { error };
    }
    await record({ ok: true, app: payload.app, ...body });
    return body;
  } catch (e) {
    // API not reachable: start it and tell the page to retry this turn shortly.
    const started = await ensureServers();
    if (started?.ok) return { error: "Starting the monitor…", retry: true };
    const error = started?.error || `Cannot reach ${cfg.apiUrl} (is the API running?)`;
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

// What the page's status pill shows: is the monitor up, and is the API key accepted?
async function siteStatus() {
  const cfg = await config();
  if (!cfg.apiKey) return { ok: false, error: "no API key: open the extension's options" };
  const r = await ensureServers();
  if (!r?.ok || r.api !== "running") return r;
  const t = await testConnection();
  return t.ok ? { ok: true, api: "running" } : { ok: false, error: t.message };
}

chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
  if (msg?.type === "turn") { sendTurn(msg.payload).then(reply); return true; }
  if (msg?.type === "test") { testConnection().then(reply); return true; }
  if (msg?.type === "site-opened") { siteStatus().then(reply); return true; }
  return false;
});

// After an install, update or reload, open chat tabs still run the previous copy of the
// content script (cut off from the extension). Inject the new copy so no refresh is needed.
chrome.runtime.onInstalled.addListener(async () => {
  const tabs = await chrome.tabs.query({ url: ["https://gemini.google.com/*", "https://chatgpt.com/*", "https://claude.ai/*"] });
  for (const tab of tabs) {
    try { await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["content.js"] }); } catch { /* tab not ready */ }
  }
});
