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
  body { font-family: system-ui, sans-serif; max-width: 860px; margin: 2rem auto;
         padding: 0 1rem; line-height: 1.45; }
  h1 { font-size: 1.5rem; } h2 { font-size: 1.15rem; margin-top: 2.2rem; }
  .step { border: 1px solid #8884; border-radius: 10px; padding: 1rem 1.2rem;
          margin: 1rem 0; }
  button { padding: .45rem .9rem; border-radius: 8px; border: 1px solid #8886;
           cursor: pointer; font-size: .95rem; background: transparent; color: inherit; }
  button.primary { background: #2563eb; color: white; border: none; }
  button.tab { border-radius: 8px 8px 0 0; border-bottom: none; }
  button.tab.active { background: #2563eb22; border-color: #2563eb; font-weight: 600; }
  button.side-tab { display: block; width: 100%; text-align: left; border-radius: 8px;
                    margin-bottom: .4rem; }
  button.side-tab.active { background: #2563eb; color: white; border-color: #2563eb; }
  input[type=text], input[type=password] { padding: .4rem .6rem; border-radius: 6px;
           border: 1px solid #8886; width: 100%; box-sizing: border-box; margin: .2rem 0 .6rem; }
  label { font-size: .85rem; opacity: .8; }
  .accounts { max-height: 320px; overflow-y: auto; border: 1px solid #8883;
              border-radius: 8px; padding: .5rem; margin: .6rem 0; }
  .accounts label { display: block; padding: .15rem .2rem .15rem 1.4rem; font-size: .92rem; opacity: 1; }
  .accounts details summary { padding: .2rem; font-size: .9rem; cursor: pointer; }
  .muted { opacity: .65; font-size: .88rem; }
  .ok { color: #16a34a; } .err { color: #dc2626; white-space: pre-wrap; }
  code, pre { background: #8882; border-radius: 6px; padding: .1rem .35rem; }
  pre { padding: .7rem; overflow-x: auto; font-size: .82rem; }
  .pill { display: inline-block; background: #8882; border-radius: 999px;
          padding: .1rem .6rem; margin: 0 .25rem .25rem 0; font-size: .85rem; }
  .pill.needs-auth { background: #f59e0b33; cursor: pointer; }
  details summary { cursor: pointer; font-weight: 600; }
  .sync-layout { display: flex; gap: 1rem; margin-top: .6rem; }
  .source-tabs { flex: 0 0 140px; display: flex; flex-direction: column; }
  .login-tabs { display: flex; gap: .4rem; flex-wrap: wrap; margin-bottom: .5rem; }
  .sync-content { flex: 1; min-width: 0; }
  #dataRecap table { width: 100%; border-collapse: collapse; font-size: .88rem; margin-top: .5rem; }
  #dataRecap th, #dataRecap td { text-align: left; padding: .25rem .4rem; border-bottom: 1px solid #8882; }
</style>
</head>
<body>
<h1>Marketing Data Hub &mdash; Setup</h1>
<p class="muted">Config: <code>__CONFIG_PATH_DISPLAY__</code></p>

<div class="step">
  <h2 style="margin-top:0">1&#41; Connect Google</h2>
  <p class="muted">Sign in with the Google account that can see your GA4 / Search
  Console properties. You can connect more than one account if your properties are
  spread across different Google logins.</p>
  <div>Connected: <span id="identities" class="muted">loading&hellip;</span></div>
  <div style="margin-top:.6rem">
    <button class="primary" onclick="connectGoogle()">+ Connect a Google account</button>
    <span id="connectMsg" class="muted"></span>
  </div>
</div>

<div class="step">
  <h2 style="margin-top:0">2&#41; Choose what to sync</h2>
  <p class="muted">Pick a source on the left, then whichever connected account it
  belongs to. Tick the properties/sites you want, then Add.</p>
  <div class="sync-layout">
    <div class="source-tabs" id="sourceTabs"></div>
    <div class="sync-content">
      <div class="login-tabs" id="loginTabs"></div>
      <div id="pickerHint" class="muted"></div>
      <input type="text" id="accountSearch" placeholder="Search by name…" oninput="renderAccountsList()">
      <div id="accountsBox" class="accounts" style="display:none"></div>
      <button class="primary" id="addBtn" style="display:none" onclick="addSelected()">Add selected</button>
      <div id="accountsMsg"></div>
    </div>
  </div>
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
  <div id="dataRecap"></div>
</div>

<div class="step">
  <h2 style="margin-top:0">5&#41; Connect Claude</h2>
  <p class="muted">Claude Desktop &rarr; Settings &rarr; Developer &rarr; Edit Config,
  add this inside <code>mcpServers</code>, save, then fully quit and reopen Claude:</p>
  <pre id="claudeSnippet"></pre>
  <button onclick="copySnippet()">Copy</button> <span id="copyMsg" class="ok"></span>
  <p style="margin-top:1.2rem">
    <button onclick="finish()">Finish &amp; close wizard</button>
  </p>
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

let identities = [];          // [{identity, label, needs_reauth}]
let currentSource = "ga4";
let currentIdentity = null;
let discovered = [];          // last /api/accounts result for the active tab

async function refreshState() {
  const s = await api("/api/state");
  identities = s.identities;

  document.getElementById("identities").innerHTML = identities.length
    ? identities.map(i => i.needs_reauth
        ? `<span class="pill needs-auth" onclick="connectGoogle('${i.identity}')" title="click to authorize">${esc(i.identity)} — click to authorize</span>`
        : `<span class="pill">${esc(i.label)}</span>`).join("")
    : "none yet";
  if (s.logins_pending.length)
    document.getElementById("identities").innerHTML +=
      ` <span class="muted">(waiting for sign-in&hellip;)</span>`;

  renderSourceTabs();
  renderLoginTabs();

  const conf = [];
  for (const [src, info] of Object.entries(s.connectors)) {
    for (const a of info.accounts) conf.push(`<span class="pill">${esc(src)}: ${esc(a.label)}</span>`);
  }
  document.getElementById("configured").innerHTML = conf.join("") || "nothing yet";
}

function renderSourceTabs() {
  const box = document.getElementById("sourceTabs");
  const sources = [["ga4", "GA4"], ["gsc", "Search Console"]];
  box.innerHTML = sources.map(([id, label]) => `
    <button class="side-tab ${id === currentSource ? "active" : ""}"
            onclick="selectSource('${id}')">${label}</button>`).join("");
}

function selectSource(source) {
  currentSource = source;
  renderSourceTabs();
  if (currentIdentity) loadAccounts();
}

function renderLoginTabs() {
  const labelled = identities.filter(i => !i.needs_reauth);
  const box = document.getElementById("loginTabs");
  const hint = document.getElementById("pickerHint");
  if (!labelled.length) {
    box.innerHTML = "";
    hint.textContent = "Connect a Google account above first.";
    document.getElementById("accountsBox").style.display = "none";
    return;
  }
  hint.textContent = "";
  if (!currentIdentity || !labelled.some(i => i.identity === currentIdentity))
    currentIdentity = labelled[0].identity;
  box.innerHTML = labelled.map(i => `
    <button class="tab ${i.identity === currentIdentity ? "active" : ""}"
            onclick="selectIdentity('${i.identity}')">${esc(i.label)}</button>`).join("");
  loadAccounts();
}

function selectIdentity(identity) {
  currentIdentity = identity;
  renderLoginTabs();
}

async function connectGoogle(identity) {
  document.getElementById("connectMsg").textContent = "opening Google sign-in… complete it in the new tab (you have a few minutes)";
  const r = await api("/api/google/connect", {method: "POST",
      body: JSON.stringify(identity ? {identity} : {})});
  if (r.error) { document.getElementById("connectMsg").innerHTML = `<span class="err">${esc(r.error)}</span>`; return; }
  const waitFor = r.identity;
  const poll = setInterval(async () => {
    const s = await api("/api/state");
    const found = s.identities.find(i => i.identity === waitFor && !i.needs_reauth);
    if (found) {
      clearInterval(poll);
      document.getElementById("connectMsg").innerHTML = `<span class="ok">connected as ${esc(found.label)} ✓</span>`;
      refreshState();
      return;
    }
    if (s.login_errors && s.login_errors[waitFor]) {
      clearInterval(poll);
      document.getElementById("connectMsg").innerHTML =
        `<span class="err">${esc(s.login_errors[waitFor])}</span> - click "+ Connect a Google account" to try again`;
    }
  }, 2000);
}

async function loadAccounts() {
  const box = document.getElementById("accountsBox");
  document.getElementById("accountsMsg").textContent = "loading (can take ~10s)…";
  box.style.display = "none";
  const r = await api(`/api/accounts?identity=${encodeURIComponent(currentIdentity)}&source=${currentSource}`);
  if (r.error) {
    document.getElementById("accountsMsg").innerHTML = `<span class="err">${esc(r.error)}</span>`;
    return;
  }
  discovered = r;
  document.getElementById("accountsMsg").textContent = "";
  box.style.display = "block";
  document.getElementById("addBtn").style.display = "inline-block";
  document.getElementById("accountSearch").value = "";
  renderAccountsList();
}

function accountRow(a, i) {
  let label = `${esc(a.name)}` + (a.id && a.id !== a.name ? ` <span class="muted">— ${esc(a.id)}</span>` : "");
  if (a.duplicate_name) {
    // a real, confirmed situation: two properties can be named IDENTICALLY
    // under the same parent, one of them completely dormant - flag it so
    // the wrong one isn't picked by mistake, same as almost happened here
    const activity = a.active_recently === false
      ? '<span class="err">no data in last 30 days - likely the wrong one</span>'
      : a.active_recently === true
        ? '<span class="ok">has recent data</span>'
        : '<span class="muted">activity unknown</span>';
    label += ` <span class="err">⚠ another account is also named "${esc(a.name)}"</span> (${activity})`;
  }
  return a.configured
    ? `<label class="muted">✓ ${label} <span class="muted">already added</span></label>`
    : `<label><input type="checkbox" data-i="${i}"> ${label}</label>`;
}

function renderAccountsList() {
  const box = document.getElementById("accountsBox");
  if (!discovered.length) { box.innerHTML = '<p class="muted">no accounts found</p>'; return; }
  const term = document.getElementById("accountSearch").value.trim().toLowerCase();
  const indexed = discovered.map((a, i) => [a, i])
      .filter(([a]) => !term || a.name.toLowerCase().includes(term) || a.id.toLowerCase().includes(term));
  if (!indexed.length) { box.innerHTML = '<p class="muted">no matches</p>'; return; }

  if (currentSource === "ga4") {
    const groups = {};
    for (const [a, i] of indexed) (groups[a.parent || a.name] = groups[a.parent || a.name] || []).push([a, i]);
    box.innerHTML = Object.entries(groups).map(([parent, rows]) => `
      <details ${term ? "open" : ""}>
        <summary>${esc(parent)} <span class="muted">(${rows.length})</span></summary>
        ${rows.map(([a, i]) => accountRow(a, i)).join("")}
      </details>`).join("");
  } else {
    box.innerHTML = indexed.map(([a, i]) => accountRow(a, i)).join("");
  }
}

async function addSelected() {
  const chosen = [...document.querySelectorAll("#accountsBox input:checked")]
      .map(cb => discovered[+cb.dataset.i]);
  if (!chosen.length) return;
  const r = await api("/api/accounts/add", {method: "POST",
      body: JSON.stringify({source: currentSource, ids: chosen.map(a => a.id), identity: currentIdentity})});
  document.getElementById("accountsMsg").innerHTML = r.error
      ? `<span class="err">${esc(r.error)}</span>`
      : `<span class="ok">added ${r.added.length} ✓</span>`;
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

async function renderDataRecap() {
  const d = await api("/api/dashboard-data");
  const el = document.getElementById("dataRecap");
  if (d.busy || !d.groups.length) { el.innerHTML = ""; return; }
  el.innerHTML = `<h3 style="font-size:.95rem;margin-bottom:.2rem">Your data so far</h3>` +
    d.groups.map(g => `
      <table>
        <tr><th colspan="3">${esc(g.source.toUpperCase())}</th></tr>
        ${g.accounts.map(a => `
          <tr><td>${esc(a.account_name)}</td><td class="muted">${esc(a.identity)}</td>
              <td>${(a.rows || 0).toLocaleString()} rows</td></tr>`).join("")}
      </table>`).join("") +
    `<p style="margin-top:.6rem"><button onclick="window.open('/dashboard','_blank')">Open full dashboard ↗</button></p>`;
}

let syncPoll = null;
async function startSync() {
  await api("/api/sync", {method: "POST"});
  document.getElementById("syncMsg").textContent = "sync started — syncing in the background, you can keep going or close this tab…";
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
    renderDataRecap();
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
  document.body.innerHTML = "<h1>All set ✓</h1><p>You can close this tab. Run <code>hub dashboard</code> anytime to check your data.</p>";
}

document.getElementById("claudeSnippet").textContent = snippet();
refreshState();
renderDataRecap();
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
