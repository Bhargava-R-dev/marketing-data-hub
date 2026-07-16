"""The single-page setup UI. Vanilla HTML/JS, served from memory; the per-run
token and config path are substituted in before serving."""
from __future__ import annotations

_PAGE = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Marketing Data Hub - Setup</title>
<style>
  :root { color-scheme: light dark; }
  body { font-family: system-ui, sans-serif; max-width: 780px; margin: 2rem auto;
         padding: 0 1rem; line-height: 1.45; }
  h1 { font-size: 1.5rem; } h2 { font-size: 1.15rem; margin-top: 2.2rem; }
  .step { border: 1px solid #8884; border-radius: 10px; padding: 1rem 1.2rem;
          margin: 1rem 0; }
  button { padding: .45rem .9rem; border-radius: 8px; border: 1px solid #8886;
           cursor: pointer; font-size: .95rem; }
  button.primary { background: #2563eb; color: white; border: none; }
  input[type=text], input[type=password] { padding: .4rem .6rem; border-radius: 6px;
           border: 1px solid #8886; width: 100%; box-sizing: border-box; margin: .2rem 0 .6rem; }
  label { font-size: .85rem; opacity: .8; }
  .accounts { max-height: 320px; overflow-y: auto; border: 1px solid #8883;
              border-radius: 8px; padding: .5rem; margin: .6rem 0; }
  .accounts label { display: block; padding: .15rem .2rem; font-size: .92rem; opacity: 1; }
  .muted { opacity: .65; font-size: .88rem; }
  .ok { color: #16a34a; } .err { color: #dc2626; white-space: pre-wrap; }
  code, pre { background: #8882; border-radius: 6px; padding: .1rem .35rem; }
  pre { padding: .7rem; overflow-x: auto; font-size: .82rem; }
  .pill { display: inline-block; background: #8882; border-radius: 999px;
          padding: .1rem .6rem; margin: 0 .25rem .25rem 0; font-size: .85rem; }
  details summary { cursor: pointer; font-weight: 600; }
</style>
</head>
<body>
<h1>Marketing Data Hub &mdash; Setup</h1>
<p class="muted">Config: <code>__CONFIG_PATH_DISPLAY__</code></p>

<div class="step">
  <h2 style="margin-top:0">1&#41; Connect Google</h2>
  <p class="muted">Sign in with the Google account that can see your GA4 / Search
  Console properties. You can connect more than one account &mdash; give each a short
  name (the first one is <code>default</code>).</p>
  <div>Connected logins: <span id="identities" class="muted">loading&hellip;</span></div>
  <div style="margin-top:.6rem">
    <label>Login name</label>
    <input type="text" id="identityName" value="default">
    <button class="primary" onclick="connectGoogle()">Connect Google account</button>
    <span id="connectMsg" class="muted"></span>
  </div>
</div>

<div class="step">
  <h2 style="margin-top:0">2&#41; Choose what to sync</h2>
  <p class="muted">Loads every GA4 property and Search Console site the selected
  login can see. Tick the ones you want, then Add.</p>
  <label>Browse login</label>
  <input type="text" id="pickIdentity" value="default" style="max-width:220px">
  <button onclick="loadAccounts()">Load accounts</button>
  <div id="accountsBox" class="accounts" style="display:none"></div>
  <button class="primary" id="addBtn" style="display:none" onclick="addSelected()">Add selected</button>
  <div id="accountsMsg"></div>
  <div style="margin-top:.6rem">Currently syncing: <span id="configured" class="muted"></span></div>
</div>

<div class="step">
  <details>
  <summary>3&#41; Ad platforms (optional) &mdash; Google Ads &amp; Meta Ads</summary>
  <div style="margin-top:.8rem">
    <h3 style="font-size:1rem">Meta Ads</h3>
    <p class="muted">Create an app at developers.facebook.com (type: Business), add the
    Marketing API, generate a long-lived token with <code>ads_read</code>. Ad account ids
    look like <code>act_1234567890</code> (comma-separate several).</p>
    <label>Access token</label>
    <input type="password" id="metaToken">
    <label>Ad account id(s)</label>
    <input type="text" id="metaAccounts" placeholder="act_123, act_456">
    <button onclick="saveMeta()">Save Meta Ads</button> <span id="metaMsg"></span>

    <h3 style="font-size:1rem;margin-top:1.2rem">Google Ads</h3>
    <p class="muted">Apply for a developer token at ads.google.com &rarr; Tools &amp;
    Settings &rarr; API Center. Customer ids look like <code>123-456-7890</code>.
    It reuses the Google login from step 1.</p>
    <label>Developer token</label>
    <input type="password" id="adsDevToken">
    <label>Customer id(s)</label>
    <input type="text" id="adsCustomers" placeholder="123-456-7890, 222-333-4444">
    <label>Manager (MCC) id &mdash; optional</label>
    <input type="text" id="adsLogin" placeholder="999-888-7777">
    <button onclick="saveGoogleAds()">Save Google Ads</button> <span id="adsMsg"></span>
  </div>
  </details>
</div>

<div class="step">
  <h2 style="margin-top:0">4&#41; Load your data</h2>
  <button class="primary" onclick="startSync()">Run first sync</button>
  <span id="syncMsg" class="muted"></span>
  <div id="syncRuns" style="margin-top:.5rem"></div>
</div>

<div class="step">
  <h2 style="margin-top:0">5&#41; Connect Claude</h2>
  <p class="muted">Claude Desktop &rarr; Settings &rarr; Developer &rarr; Edit Config,
  add this inside <code>mcpServers</code>, save, then fully quit and reopen Claude:</p>
  <pre id="claudeSnippet"></pre>
  <button onclick="copySnippet()">Copy</button> <span id="copyMsg" class="ok"></span>
  <p style="margin-top:1.2rem"><button onclick="finish()">Finish &amp; close wizard</button></p>
</div>

<script>
const TOKEN = "__RUN_TOKEN__";
const CONFIG_PATH = "__CONFIG_PATH__";
const H = {"Content-Type": "application/json", "X-Setup-Token": TOKEN};

async function api(path, opts) {
  const r = await fetch(path, Object.assign({headers: H}, opts || {}));
  return r.json();
}
function esc(s) { return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;"); }

async function refreshState() {
  const s = await api("/api/state");
  document.getElementById("identities").innerHTML =
    (s.identities.length ? s.identities.map(i => `<span class="pill">${esc(i)}</span>`).join("")
                         : "none yet") +
    (s.logins_pending.length ? ` <span class="muted">(waiting for sign-in: ${s.logins_pending.join(", ")}&hellip;)</span>` : "");
  const conf = [];
  for (const [src, info] of Object.entries(s.connectors)) {
    for (const a of info.accounts) conf.push(`<span class="pill">${esc(src)}: ${esc(a.label)}</span>`);
  }
  document.getElementById("configured").innerHTML = conf.join("") || "nothing yet";
}

async function connectGoogle() {
  const identity = document.getElementById("identityName").value.trim() || "default";
  document.getElementById("connectMsg").textContent = "opening Google sign-in… complete it in the new tab";
  const r = await api("/api/google/connect", {method: "POST", body: JSON.stringify({identity})});
  if (r.error) document.getElementById("connectMsg").innerHTML = `<span class="err">${esc(r.error)}</span>`;
  const poll = setInterval(async () => {
    const s = await api("/api/state");
    if (s.identities.includes(identity)) {
      clearInterval(poll);
      document.getElementById("connectMsg").innerHTML = '<span class="ok">connected ✓</span>';
      document.getElementById("pickIdentity").value = identity;
      refreshState();
    }
  }, 2000);
}

let discovered = [];
async function loadAccounts() {
  const identity = document.getElementById("pickIdentity").value.trim() || "default";
  document.getElementById("accountsMsg").textContent = "loading (can take ~10s)…";
  const r = await api(`/api/accounts?identity=${encodeURIComponent(identity)}`);
  const box = document.getElementById("accountsBox");
  if (r.error) { document.getElementById("accountsMsg").innerHTML = `<span class="err">${esc(r.error)}</span>`; return; }
  discovered = r;
  document.getElementById("accountsMsg").textContent = "";
  box.style.display = "block";
  document.getElementById("addBtn").style.display = "inline-block";
  box.innerHTML = r.map((a, i) => {
    const label = `${a.source.toUpperCase()} — ${esc(a.name)}` +
                  (a.parent && a.parent !== a.name ? ` <span class="muted">(${esc(a.parent)})</span>` : "");
    return a.configured
      ? `<label class="muted">✓ ${label} <span class="muted">already added</span></label>`
      : `<label><input type="checkbox" data-i="${i}"> ${label}</label>`;
  }).join("");
}

async function addSelected() {
  const identity = document.getElementById("pickIdentity").value.trim() || "default";
  const chosen = [...document.querySelectorAll("#accountsBox input:checked")]
      .map(cb => discovered[+cb.dataset.i]);
  if (!chosen.length) return;
  const bySource = {};
  chosen.forEach(a => (bySource[a.source] = bySource[a.source] || []).push(a.id));
  const msgs = [];
  for (const [source, ids] of Object.entries(bySource)) {
    const r = await api("/api/accounts/add", {method: "POST",
        body: JSON.stringify({source, ids, identity})});
    msgs.push(r.error ? `<span class="err">${esc(r.error)}</span>`
                      : `<span class="ok">${source}: added ${r.added.length} ✓</span>`);
  }
  document.getElementById("accountsMsg").innerHTML = msgs.join(" ");
  refreshState(); loadAccounts();
}

async function saveMeta() {
  const accounts = document.getElementById("metaAccounts").value
      .split(",").map(s => s.trim()).filter(Boolean);
  const r = await api("/api/connector/options", {method: "POST", body: JSON.stringify({
    source: "meta_ads",
    options: {access_token: document.getElementById("metaToken").value.trim(),
              ad_account_ids: accounts}})});
  document.getElementById("metaMsg").innerHTML = r.error
      ? `<span class="err">${esc(r.error)}</span>` : '<span class="ok">saved ✓</span>';
}

async function saveGoogleAds() {
  const customers = document.getElementById("adsCustomers").value
      .split(",").map(s => s.trim()).filter(Boolean);
  const r = await api("/api/connector/options", {method: "POST", body: JSON.stringify({
    source: "google_ads",
    options: {developer_token: document.getElementById("adsDevToken").value.trim(),
              customer_ids: customers,
              login_customer_id: document.getElementById("adsLogin").value.trim()}})});
  document.getElementById("adsMsg").innerHTML = r.error
      ? `<span class="err">${esc(r.error)}</span>` : '<span class="ok">saved ✓</span>';
}

let syncPoll = null;
async function startSync() {
  await api("/api/sync", {method: "POST"});
  document.getElementById("syncMsg").textContent = "sync started — this can take a few minutes…";
  if (syncPoll) clearInterval(syncPoll);
  syncPoll = setInterval(async () => {
    const s = await api("/api/sync/status");
    document.getElementById("syncRuns").innerHTML = s.runs.map(r =>
      r.status === "success"
        ? `<div class="ok">✓ ${esc(r.source)}: ${r.rows.toLocaleString()} rows</div>`
        : r.status === "running"
          ? `<div class="muted">⏳ ${esc(r.source)}: syncing…</div>`
          : `<div class="err">✗ ${esc(r.source)}: ${esc(r.error || r.status)}</div>`
    ).join("") || '<div class="muted">⏳ starting…</div>';
    if (!s.in_progress && s.runs.length) {
      clearInterval(syncPoll);
      document.getElementById("syncMsg").innerHTML = '<span class="ok">done ✓</span>';
      refreshState();
    }
  }, 3000);
}

function snippet() {
  return JSON.stringify({"marketing-hub": {command: "python",
    args: ["-m", "hub.cli", "mcp", "--config", CONFIG_PATH]}}, null, 2)
    .replace(/^{\n|\n}$/g, "");
}
function copySnippet() {
  navigator.clipboard.writeText(snippet());
  document.getElementById("copyMsg").textContent = "copied ✓";
}
async function finish() {
  await api("/api/shutdown", {method: "POST"});
  document.body.innerHTML = "<h1>All set ✓</h1><p>You can close this tab.</p>";
}

document.getElementById("claudeSnippet").textContent = snippet();
refreshState();
</script>
</body>
</html>
"""


def render_page(run_token: str, config_path: str) -> str:
    # json-style escaping for the path inside JS strings; raw for display
    return (_PAGE
            .replace("__RUN_TOKEN__", run_token)
            .replace("__CONFIG_PATH_DISPLAY__", config_path)
            .replace("__CONFIG_PATH__", config_path.replace("\\", "\\\\")))
