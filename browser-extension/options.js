const DEFAULTS = { apiUrl: "http://127.0.0.1:8000", apiKey: "", project: "", sites: {}, onlyNew: true, showBadges: true };
const $ = (id) => document.getElementById(id);
const status = (msg, ok = true) => { $("status").textContent = msg; $("status").style.color = ok ? "" : "#d03b3b"; };

chrome.storage.local.get(DEFAULTS, (s) => {
  $("apiUrl").value = s.apiUrl;
  $("apiKey").value = s.apiKey;
  $("project").value = s.project;
  $("onlyNew").checked = s.onlyNew;
  $("showBadges").checked = s.showBadges;
  document.querySelectorAll("[data-site]").forEach((c) => { c.checked = s.sites[c.dataset.site] !== false; });
});

async function save() {
  const apiUrl = ($("apiUrl").value.trim() || DEFAULTS.apiUrl).replace(/\/$/, "");
  let origin;
  try { origin = new URL(apiUrl).origin; } catch { status("API URL is not a valid URL", false); return false; }
  // Ask for access to a non-default API host (localhost:8000 is granted at install).
  if (!/^http:\/\/(127\.0\.0\.1|localhost):8000$/.test(origin)) {
    const granted = await chrome.permissions.request({ origins: [`${origin}/*`] });
    if (!granted) { status(`Permission to reach ${origin} was not granted`, false); return false; }
  }
  const sites = {};
  document.querySelectorAll("[data-site]").forEach((c) => { sites[c.dataset.site] = c.checked; });
  await chrome.storage.local.set({
    apiUrl, apiKey: $("apiKey").value.trim(), project: $("project").value.trim(),
    sites, onlyNew: $("onlyNew").checked, showBadges: $("showBadges").checked,
  });
  status("Saved. Reload open chat tabs to apply.");
  return true;
}

$("save").addEventListener("click", save);
$("test").addEventListener("click", async () => {
  if (!(await save())) return;
  status("Testing…");
  chrome.runtime.sendMessage({ type: "test" }, (r) => status(r?.ok ? "Connected to your workspace ✓" : `Not connected: ${r?.message}`, !!r?.ok));
});
