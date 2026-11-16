// Agent Observability chat monitor: content script.
//
// Watches the chat page, and when an answer has finished (and stopped changing),
// sends {user message, answer} to the background worker, which forwards it to
// your dashboard. The check result is shown as a small line under the answer.
//
// Site structure changes over time; each site's reader is kept small below.
(() => {
  const VERSION = "1.2.4";
  // One copy per page. A newer copy (injected after an extension update) replaces an older one.
  const existing = document.querySelector("[data-aobs-monitor]");
  if (existing && existing.getAttribute("data-aobs-monitor") === VERSION) return;
  existing?.remove();
  // Pills from copies before 1.2.0 carry no marker: recognise them by their shadow content.
  document.querySelectorAll("body > div:not([data-aobs-monitor])").forEach((d) => {
    if (d.shadowRoot?.querySelector(".p > .d + .t")) d.remove();
  });

  const STABLE_MS = 1500;   // answer text must stop changing for this long
  const SCAN_MS = 1000;
  const RETRY_MS = 4000;    // while the local monitor starts, retry a turn this often
  const RETRY_LIMIT = 45;   // about 3 minutes

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

    // Verified on the live site (logged out): message ids, user text, answer text, completion.
    "chatgpt.com": {
      app: "chatgpt-web",
      conversation: () => pathId(/\/(?:c|uc)\/([^/?#]+)/),
      model: () => {
        const slug = document.querySelector("[data-message-model-slug]")?.getAttribute("data-message-model-slug");
        return slug || "ChatGPT (web)";
      },
      // ChatGPT's markup differs between signed-in and signed-out pages and changes over
      // time, so several layouts are tried in order; the first that finds messages wins.
      turns() {
        const generating = () => !!document.querySelector('[data-testid="stop-button"], button[aria-label^="Stop"]');
        const strip = (s) => s.replace(/^(ChatGPT said|You said|ChatGPT|You):\s*/i, "").trim();
        let out = [], lastUser = "";
        // 0. signed-in layout (2026): turns are [data-turn-key]; an answer is [data-response-body=<message id>]
        //    holding [data-markdown-text-style="assistant-message"]; the turn says data-talvt-turn-state="complete".
        const bodies = new Set();
        document.querySelectorAll('[data-markdown-text-style="assistant-message"]').forEach((md) => {
          const body = md.closest("[data-response-body]") || md.closest("[data-chatgpt-selection-message-id]") || md;
          if (bodies.has(body)) return;
          bodies.add(body);
          const turn = body.closest("[data-turn-key]");
          const userEl = turn?.querySelector("[data-user-message-bubble] .whitespace-pre-wrap, [data-user-message-bubble]");
          if (userEl) lastUser = text(userEl);
          const parts = [...body.querySelectorAll('[data-markdown-text-style="assistant-message"]')].map(text).filter(Boolean);
          const state = body.closest("[data-talvt-turn-state]")?.getAttribute("data-talvt-turn-state");
          out.push({
            id: body.getAttribute("data-response-body") || body.getAttribute("data-chatgpt-selection-message-id") || turn?.getAttribute("data-turn-key") || "",
            user: lastUser, response: parts.join("\n\n") || text(md),
            done: state ? state === "complete" : !generating(), el: body,
          });
        });
        if (out.length) return out;
        // 1. message role markers (one element per message)
        document.querySelectorAll("li[data-message-role], [data-message-author-role]").forEach((el) => {
          const role = el.getAttribute("data-message-role") || el.getAttribute("data-message-author-role");
          if (role === "user") { lastUser = text(el.querySelector("[data-user-message-copy], [data-user-message-bubble], .whitespace-pre-wrap") || el); return; }
          if (role !== "assistant" || el.parentElement?.closest('[data-message-author-role="assistant"]')) return;
          const response = text(el.querySelector("[data-assistant-markdown], .markdown") || el);
          const id = el.getAttribute("data-message-id") || el.id;
          const done = el.hasAttribute("data-message-complete") || (!el.hasAttribute("data-message-role") && !generating());
          out.push({ id, user: lastUser, response, done, el });
        });
        if (out.length) return out;
        // 2. conversation-turn blocks (one per turn), role from data-turn or the hidden "You said / ChatGPT said" label
        lastUser = "";
        document.querySelectorAll('article[data-testid^="conversation-turn"], section[data-turn], article[data-turn], [data-turn-id]').forEach((el) => {
          if (el.parentElement?.closest('[data-turn-id], article[data-testid^="conversation-turn"]')) return;
          const label = text(el.querySelector(".sr-only, h5, h6"));
          const role = el.getAttribute("data-turn") || (/chatgpt said/i.test(label) ? "assistant" : /you said/i.test(label) ? "user" : "");
          if (role === "user") { lastUser = strip(text(el.querySelector(".whitespace-pre-wrap") || el)); return; }
          if (role !== "assistant") return;
          const md = el.querySelector(".markdown, [class*='markdown']");
          out.push({ id: el.getAttribute("data-turn-id") || el.getAttribute("data-testid") || "", user: lastUser,
                     response: strip(text(md || el)), done: !generating(), el });
        });
        if (out.length) return out;
        // 3. last resort: answer text blocks, user text from the nearest earlier message bubble
        const bubbles = [...document.querySelectorAll(".whitespace-pre-wrap")];
        document.querySelectorAll("main .markdown, main [class*='markdown prose']").forEach((md, i) => {
          if (md.parentElement?.closest(".markdown")) return;
          const before = bubbles.filter((b) => b.compareDocumentPosition(md) & Node.DOCUMENT_POSITION_FOLLOWING && !b.closest(".markdown"));
          out.push({ id: "", user: before.length ? text(before[before.length - 1]) : "", response: text(md), done: !generating(), el: md });
        });
        return out;
      },
    },

    // claude.ai requires sign-in, so this reader follows the site's known markup
    // (current and older class names) rather than a live test.
    "claude.ai": {
      app: "claude-web",
      conversation: () => pathId(/\/chat\/([^/?#]+)/),
      model: () => {
        const b = document.querySelector('[data-testid="model-selector-dropdown"]');
        const name = b ? text(b).replace(/\s+/g, " ").replace(/^Claude\s+/i, "") : "";   // e.g. "Opus 5.5 Medium"
        return name ? `Claude ${name}`.slice(0, 120) : "Claude (web)";
      },
      turns() {
        const out = [];
        let lastUser = "";
        const ASSISTANT = '.font-claude-response, .font-claude-message, [data-testid="assistant-message"]';
        let n = 0;
        document.querySelectorAll(`[data-testid="user-message"], ${ASSISTANT}`).forEach((el) => {
          if (el.matches('[data-testid="user-message"]')) { lastUser = text(el); return; }
          if (el.parentElement?.closest(ASSISTANT)) return;   // nested match inside the same answer
          const streaming = el.closest('[data-is-streaming="true"]');
          // No message id on the page: the answer's position in its chat identifies it (see turnId).
          out.push({ id: `pos:${n++}`, user: lastUser, response: text(el), done: !streaming, el });
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
  let openedAt = Date.now(); // when the current conversation was opened
  const HISTORY_MS = 8000;  // chat sites render old messages a moment after the page loads
  let freshChat = false;    // a brand-new chat: nothing in it is history

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

  // A stable key for the current chat. A brand-new chat only gets its address after the
  // first message, so the key it had before carries over to the address (per tab).
  let pendingKey = null;
  function chatKey() {
    const conv = site.conversation();
    let map = {};
    try { map = JSON.parse(sessionStorage.getItem("aobsChatKeys") || "{}"); } catch { /* blocked */ }
    if (!conv) return (pendingKey = pendingKey || `new-${Date.now().toString(36)}`);
    if (pendingKey && !map[conv]) {
      map[conv] = pendingKey;
      try { sessionStorage.setItem("aobsChatKeys", JSON.stringify(map)); } catch { /* blocked */ }
    }
    pendingKey = null;
    return map[conv] || conv;
  }

  function turnId(t, i) {
    if (t.id && t.id.startsWith("pos:")) return `${chatKey()}#${t.id.slice(4)}`;
    return t.id || `${chatKey()}#${i}`;
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
    const label = result.retry ? "Starting the monitor… this answer will be checked in a moment" :
      result.error ? `Not monitored: ${result.error}` :
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
      freshChat = continuingNewChat || convKey === "";
      openedAt = now;
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
      if (!seen.has(id) && t.done && settings.onlyNew && !freshChat && now - openedAt < HISTORY_MS) {
        // Already finished when it first appeared, right after the chat opened: an old message
        // rendered late, not a new answer (new answers are first seen while still being written).
        seen.set(id, { hash: h, since: 0, sentHash: h, tries: 0, retryAt: 0 });
        continue;
      }
      const s = seen.get(id) || { hash: "", since: now, sentHash: "", tries: 0, retryAt: 0 };
      if (s.hash !== h) { s.hash = h; s.since = now; s.tries = 0; }
      seen.set(id, s);
      if (!t.done || s.sentHash === h || now - s.since < STABLE_MS || now < s.retryAt) continue;
      s.sentHash = h; // also covers regenerated answers: new text, same turn id
      const result = await send({
        app: site.app, turn_id: id, conversation_id: site.conversation(), model: site.model(),
        user_message: t.user.slice(0, 100000), response: t.response.slice(0, 200000),
      });
      if (result?.error && !result.retry) monitorState = { ok: false, msg: result.error };
      else if (result && !result.error) monitorState = { ok: true, msg: "" };
      if (result?.retry && s.tries < RETRY_LIMIT) {
        // The monitor is starting up: keep this turn and send it again in a few seconds.
        s.tries += 1;
        s.sentHash = "";
        s.retryAt = Date.now() + RETRY_MS;
      }
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

  // ---------------------------------------------------------------- status pill
  // A small corner indicator so it is obvious the monitor is on, and what it can see.
  const pill = (() => {
    const host = document.createElement("div");
    host.setAttribute("data-aobs-monitor", VERSION);
    // Top centre: chat sites keep their composer and send button at the bottom, account menus at the corners.
    host.style.cssText = "position:fixed; top:10px; left:50%; transform:translateX(-50%); z-index:2147483647;";
    const root = host.attachShadow({ mode: "open" });
    root.innerHTML = `<style>
      .p { font: 12px/1.3 system-ui, sans-serif; color: #e8e8e8; background: rgba(24,24,28,.92); border: 1px solid rgba(255,255,255,.14);
           border-radius: 999px; padding: 6px 12px 6px 10px; display: flex; gap: 8px; align-items: center; box-shadow: 0 6px 24px rgba(0,0,0,.35);
           transition: opacity .4s; cursor: default; max-width: 360px; }
      .d { width: 8px; height: 8px; border-radius: 50%; flex: none; }
      .p.quiet { opacity: .35; } .p:hover { opacity: 1; }
    </style><div class="p"><span class="d"></span><span class="t"></span></div>`;
    (document.body || document.documentElement).appendChild(host);
    const box = root.querySelector(".p"), dot = root.querySelector(".d"), label = root.querySelector(".t");
    let shownAt = Date.now();
    return {
      set(color, msg, title = "") {
        if (label.textContent !== msg) { label.textContent = msg; shownAt = Date.now(); box.classList.remove("quiet"); }
        dot.style.background = color; box.title = title;
      },
      tick() { if (Date.now() - shownAt > 8000) box.classList.add("quiet"); },
      host,
    };
  })();
  let monitorState = { ok: null, msg: "Chat Monitor: connecting…" };

  // If the page clearly shows a conversation but the reader finds no answers, the site's
  // layout has changed. Save a structure-only snapshot (element names and data-* markers,
  // never any text) so the reader can be fixed; it is kept in the extension's local storage.
  const loadedAt = Date.now();
  let diagSavedFor = null;   // page path the last snapshot was taken on
  function saveLayoutSnapshot() {
    const mask = (v) => v.replace(/[0-9a-f]{8}-[0-9a-f-]{27,}/gi, "<id>").replace(/\d+/g, "#").slice(0, 40);
    const KEEP = /markdown|prose|message|turn|whitespace|bubble|response|query|conversation/i;
    const sig = (el) => {
      const attrs = [...el.attributes].filter((a) => a.name.startsWith("data-") || a.name === "role")
        .map((a) => `${a.name}=${mask(a.value)}`);
      const cls = [...el.classList].filter((c) => KEEP.test(c)).slice(0, 4);
      return `${el.tagName.toLowerCase()}${cls.length ? "." + cls.join(".") : ""}${attrs.length ? "[" + attrs.join(" ") + "]" : ""}`;
    };
    const counts = new Map();
    const all = [...(document.querySelector("main") || document.body).querySelectorAll("*")].slice(0, 6000);
    for (const el of all) {
      if (![...el.attributes].some((a) => a.name.startsWith("data-")) && ![...el.classList].some((c) => KEEP.test(c))) continue;
      const s = sig(el);
      counts.set(s, (counts.get(s) || 0) + 1);
    }
    // ancestors of the element holding the most text (the latest answer, most likely)
    let best = null, bestLen = 0;
    for (const el of all) {
      const own = [...el.childNodes].filter((c) => c.nodeType === 3).reduce((n, c) => n + c.textContent.trim().length, 0);
      if (own > bestLen) { best = el; bestLen = own; }
    }
    const chain = [];
    for (let el = best; el && el !== document.body && chain.length < 12; el = el.parentElement) chain.push(sig(el));
    const snapshot = { site: site.app, at: Date.now(), path: mask(location.pathname),
      markers: [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 80).map(([s, c]) => `${c}× ${s}`), answerChain: chain };
    try { ext.storage.local.set({ layoutSnapshot: snapshot }); } catch { /* reloaded */ }
    diagSavedFor = location.pathname;
  }

  function updatePill() {
    if (!ext) return;
    const n = site.turns().filter((t) => t.response).length;
    // Snapshot once per conversation (path), when it has visible content but no answers were found.
    const area = document.querySelector("main") || document.body;
    if (!n && diagSavedFor !== location.pathname && site.conversation() && Date.now() - loadedAt > 10000 &&
        (area.innerText || "").length > 400) saveLayoutSnapshot();
    const seenLabel = `${n} answer${n === 1 ? "" : "s"} on this page`;
    const count = `(${n} on page)`;
    if (!settings.enabled) pill.set("#c98500", "Chat Monitor paused", "Resume it from the extension's toolbar button");
    else if (monitorState.ok === false) pill.set("#d03b3b", `Chat Monitor: ${monitorState.msg}`, seenLabel);
    else if (monitorState.ok === null) pill.set("#888", monitorState.msg, seenLabel);
    else pill.set("#0ca30c", `Chat Monitor on · checking new answers ${count}`,
      `v${VERSION}. Answers already on screen when you open a chat are treated as history and not re-checked.`);
    pill.tick();
  }
  const setState = (r) => {
    if (r?.ok === false || r?.error) monitorState = { ok: false, msg: r.error || "not connected" };
    else if (r?.api === "starting") monitorState = { ok: null, msg: "Chat Monitor: starting the local monitor…" };
    else if (r) monitorState = { ok: true, msg: "" };
  };

  // Opening the chat site starts the local monitor, so it is ready by the first answer.
  const checkMonitor = () => {
    try { ext?.runtime.sendMessage({ type: "site-opened" }, (r) => { void ext.runtime.lastError; setState(r); }); } catch { /* reloaded */ }
  };
  checkMonitor();
  const monitorTimer = setInterval(checkMonitor, 20000);

  const timers = [];
  const alive = () => {
    // Cut off from the extension (it was reloaded or removed), or replaced by a newer copy: stop.
    if (ext && !(globalThis.chrome && chrome.runtime && chrome.runtime.id) || !pill.host.isConnected) {
      timers.forEach(clearInterval);
      pill.host.remove();
      return false;
    }
    return true;
  };
  timers.push(monitorTimer);
  timers.push(setInterval(() => { if (alive()) { scan().catch(() => {}); updatePill(); } }, SCAN_MS));

  // Exposed for testing in a page without the extension.
  window.__aobsChatMonitorDebug = { site: site.app, turns: () => site.turns(), scan, settings: () => settings };
})();
