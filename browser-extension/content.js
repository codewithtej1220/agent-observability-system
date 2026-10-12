// Agent Observability chat monitor: content script.
//
// Watches the chat page, and when an answer has finished (and stopped changing),
// sends {user message, answer} to the background worker, which forwards it to
// your dashboard. The check result is shown as a small line under the answer.
//
// Site structure changes over time; each site's reader is kept small below.
(() => {
  if (window.__aobsChatMonitor) return;
  window.__aobsChatMonitor = true;

  const STABLE_MS = 1500;   // answer text must stop changing for this long
  const SCAN_MS = 1000;

  const text = (el) => (el ? (el.innerText || "").trim() : "");
  const hash = (s) => {
    let h = 2166136261;
    for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
    return (h >>> 0).toString(36);
  };
  const pathId = (re) => (location.pathname.match(re) || [])[1] || "";

  // ---------------------------------------------------------------- site readers
  // Each returns [{id, user, response, done, el}] in page order.
  const SITES = {
    "gemini.google.com": {
      app: "gemini-web",
      conversation: () => pathId(/\/app\/([^/?#]+)/),
      model: () => {
        const b = [...document.querySelectorAll("button")].find((x) => {
          const t = text(x);
          return t && t.length < 30 && /^(fast|thinking|pro|flash|flash-lite|[\d.]+\s*\w+)$/i.test(t);
        });
        return b ? `Gemini ${text(b)}` : "Gemini (web)";
      },
      turns() {
        const out = [];
        let lastUser = "";
        document.querySelectorAll("user-query, model-response").forEach((el) => {
          if (el.tagName.toLowerCase() === "user-query") {
            const lines = [...el.querySelectorAll(".query-text-line")].map(text).filter(Boolean);
            lastUser = lines.length ? lines.join("\n") : text(el).replace(/^You said\s*/i, "");
            return;
          }
          const content = el.querySelector("message-content");
          const id = (content?.id || "").replace(/^message-content-id-/, "");
          const response = text(content?.querySelector(".markdown") || content);
          const busy = el.querySelector('[aria-busy="true"]');
          out.push({ id, user: lastUser, response, done: !!el.querySelector("message-actions") && !busy, el });
        });
        return out;
      },
    },

    "chatgpt.com": {
      app: "chatgpt-web",
      conversation: () => pathId(/\/(?:c|uc)\/([^/?#]+)/),
      model: () => {
        const slug = document.querySelector("[data-message-model-slug]")?.getAttribute("data-message-model-slug");
        return slug || "ChatGPT (web)";
      },
      turns() {
        const out = [];
        let lastUser = "";
        document.querySelectorAll("li[data-message-role], [data-message-author-role]").forEach((el) => {
          const role = el.getAttribute("data-message-role") || el.getAttribute("data-message-author-role");
          if (role === "user") {
            lastUser = text(el.querySelector("[data-user-message-copy], [data-user-message-bubble]") || el);
            return;
          }
          if (role !== "assistant") return;
          const response = text(el.querySelector("[data-assistant-markdown], .markdown") || el);
          const id = el.getAttribute("data-message-id") || el.id;
          const done = el.hasAttribute("data-message-complete") ||
            (!el.hasAttribute("data-message-role") && !document.querySelector('[data-testid="stop-button"]'));
          out.push({ id, user: lastUser, response, done, el });
        });
        return out;
      },
    },

    // claude.ai requires sign-in, so this reader is based on the site's known
    // structure and has not been verified against the live page.
    "claude.ai": {
      app: "claude-web",
      conversation: () => pathId(/\/chat\/([^/?#]+)/),
      model: () => "Claude (web)",
      turns() {
        const out = [];
        let lastUser = "";
        document.querySelectorAll('[data-testid="user-message"], .font-claude-response, .font-claude-message').forEach((el, i) => {
          if (el.matches('[data-testid="user-message"]')) { lastUser = text(el); return; }
          const streaming = el.closest('[data-is-streaming="true"]');
          out.push({ id: "", user: lastUser, response: text(el), done: !streaming, el, index: i });
        });
        return out;
      },
    },
  };

  const site = SITES[location.hostname];
  if (!site) return;

  // ---------------------------------------------------------------- state
  let settings = { showBadges: true, onlyNew: true, enabled: true };
  const seen = new Map();   // turnId -> {hash, since, sentHash}
  let baselineFor = null;   // conversation key whose existing turns were marked as already seen

  const ext = globalThis.chrome && chrome.runtime && chrome.runtime.id ? chrome : null;
  if (!ext && window.__aobsTestSettings) settings = { ...settings, ...window.__aobsTestSettings };
  const send = (payload) => new Promise((resolve) => {
    // Outside the extension (tests run the script in the page): hand turns to a test hook.
    if (!ext) return resolve(window.__aobsTestSend ? window.__aobsTestSend(payload) : { error: "Extension context unavailable" });
    try {
      ext.runtime.sendMessage({ type: "turn", payload }, (resp) => resolve(resp || { error: ext.runtime.lastError?.message }));
    } catch (e) {
      resolve({ error: String(e) }); // extension reloaded: page needs a refresh
    }
  });

  function turnId(t, i) {
    return t.id || `${site.conversation() || location.pathname}#${i}`;
  }

  function badge(t, result) {
    if (!settings.showBadges || !t.el?.isConnected) return;
    let b = t.el.querySelector(":scope > .aobs-badge") || t.el.nextElementSibling;
    if (!b || !b.classList?.contains("aobs-badge")) {
      b = document.createElement("div");
      b.className = "aobs-badge";
      b.style.cssText = "font: 12px/1.4 system-ui, sans-serif; margin: 4px 0 10px; padding: 3px 8px; border-radius: 6px;" +
        "display: inline-flex; gap: 6px; align-items: center; border: 1px solid rgba(128,128,128,.35); opacity: .9;";
      t.el.insertAdjacentElement("afterend", b);
    }
    const sev = result.severity;
    const color = sev === "critical" ? "#d03b3b" : sev === "warning" ? "#c98500" : sev === "ok" ? "#0ca30c" : "#888";
    const label = result.error ? `Not monitored: ${result.error}` :
      result.skipped ? "Monitoring paused" :
      sev === "ok" ? "Checked: no issues" : `${sev === "critical" ? "Critical" : "Warning"}: ${(result.failed || []).join(", ")}`;
    b.textContent = "";
    const dot = document.createElement("span");
    dot.style.cssText = `width:8px;height:8px;border-radius:50%;background:${color};display:inline-block`;
    const span = document.createElement("span");
    span.textContent = label;
    b.append(dot, span);
    if (result.url) {
      const a = document.createElement("a");
      a.href = result.url; a.target = "_blank"; a.rel = "noopener"; a.textContent = "View";
      a.style.cssText = "color: inherit; text-decoration: underline;";
      b.append(a);
    }
  }

  async function scan() {
    if (!settings.enabled) return;
    const turns = site.turns();
    const convKey = site.conversation(); // "" on a new, not-yet-saved chat
    const now = Date.now();

    if (baselineFor !== convKey) {
      // A new chat gets its id only after the first message: that is the same chat
      // continuing, not a switch to an old one, so nothing on screen is history.
      const continuingNewChat = baselineFor === "";
      if (settings.onlyNew && !continuingNewChat) {
        // Opened an existing conversation: what is already on screen is history.
        turns.forEach((t, i) => { if (t.done) seen.set(turnId(t, i), { hash: hash(t.response), since: 0, sentHash: hash(t.response) }); });
        baselineFor = convKey;
        return;
      }
      baselineFor = convKey;
    }

    for (let i = 0; i < turns.length; i++) {
      const t = turns[i];
      if (!t.response) continue;
      const id = turnId(t, i);
      const h = hash(t.response);
      const s = seen.get(id) || { hash: "", since: now, sentHash: "" };
      if (s.hash !== h) { s.hash = h; s.since = now; }
      seen.set(id, s);
      if (!t.done || s.sentHash === h || now - s.since < STABLE_MS) continue;
      s.sentHash = h; // also covers regenerated answers: new text, same turn id
      const result = await send({
        app: site.app, turn_id: id, conversation_id: site.conversation(), model: site.model(),
        user_message: t.user.slice(0, 100000), response: t.response.slice(0, 200000),
      });
      badge(t, result || {});
    }
  }

  function loadSettings() {
    if (!ext) return;
    ext.storage.local.get({ showBadges: true, onlyNew: true, paused: false, sites: {} }, (s) => {
      settings = { showBadges: s.showBadges, onlyNew: s.onlyNew, enabled: !s.paused && s.sites[site.app] !== false };
    });
  }
  loadSettings();
  ext?.storage.onChanged.addListener(loadSettings);

  setInterval(() => { scan().catch(() => {}); }, SCAN_MS);

  // Exposed for testing in a page without the extension.
  window.__aobsChatMonitorDebug = { site: site.app, turns: () => site.turns(), scan, settings: () => settings };
})();
