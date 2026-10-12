const $ = (id) => document.getElementById(id);
const COLORS = { ok: "#0ca30c", warning: "#c98500", critical: "#d03b3b" };
const APPS = { "gemini-web": "Gemini", "chatgpt-web": "ChatGPT", "claude-web": "Claude" };

function ago(t) {
  const s = (Date.now() - t) / 1000;
  return s < 60 ? "just now" : s < 3600 ? `${Math.floor(s / 60)}m ago` : `${Math.floor(s / 3600)}h ago`;
}

function render() {
  chrome.storage.local.get({ apiKey: "", paused: false, stats: { sent: 0, issues: 0, recent: [] } }, (s) => {
    const configured = !!s.apiKey;
    $("state").textContent = !configured ? "Not set up" : s.paused ? "Paused" : "Monitoring";
    $("state").style.color = !configured ? "#d03b3b" : s.paused ? "#c98500" : COLORS.ok;
    $("pause").textContent = s.paused ? "Resume" : "Pause";
    $("pause").disabled = !configured;
    $("counts").textContent = `${s.stats.sent} chats checked · ${s.stats.issues} with issues`;
    $("error").textContent = s.stats.lastError ? `${s.stats.lastError.message} (${ago(s.stats.lastError.at)})` : "";
    $("recent").innerHTML = "";
    for (const r of s.stats.recent) {
      const li = document.createElement("li");
      const dot = document.createElement("span");
      dot.className = "dot";
      dot.style.background = COLORS[r.severity] || "#888";
      const a = document.createElement("a");
      a.href = r.url || "#"; a.target = "_blank";
      a.textContent = `${APPS[r.app] || r.app}: ${r.severity === "ok" ? "no issues" : (r.failed || []).join(", ")}`;
      const when = document.createElement("div");
      when.className = "muted"; when.textContent = ago(r.at);
      li.append(dot, a, when);
      $("recent").append(li);
    }
  });
}

$("pause").addEventListener("click", () => chrome.storage.local.get({ paused: false }, (s) => chrome.storage.local.set({ paused: !s.paused }, render)));
$("options").addEventListener("click", (e) => { e.preventDefault(); chrome.runtime.openOptionsPage(); });
$("dashboard").addEventListener("click", (e) => { e.preventDefault(); chrome.tabs.create({ url: "http://localhost:5173/llm/calls?source=browser" }); });
render();
