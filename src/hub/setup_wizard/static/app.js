/* Marketing Data Hub setup wizard v3 - vanilla JS, no build step. */
const H = {"Content-Type": "application/json", "X-Setup-Token": TOKEN};
const STEPS = ["Welcome", "Connect Google", "Choose accounts", "Sync", "Connect Claude", "Done"];
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");
const SOURCE_ICONS = {ga4: "ga4.png", gsc: "gsc.png"};
const sourceIcon = (s) => SOURCE_ICONS[s] ? `<img class="src-icon" src="/static/icons/${SOURCE_ICONS[s]}" alt="${esc(s)}">` : "";

async function api(path, opts) {
  const r = await fetch(path, Object.assign({headers: H}, opts || {}));
  const body = await r.json();
  if (!r.ok) throw new Error(body.detail || `Request failed (${r.status})`);
  return body;
}

// ---------------------------------------------------------------- state
let S = null;                 // last /api/state
let step = 0;                 // current step index
let src = "ga4", ident = null, discovered = [], lastReq = 0, selected = new Set();
let pollTimer = null;

async function refresh() { S = await api("/api/state"); renderStepper(); }

function connectedLogins() { return (S?.identities || []).filter(i => !i.needs_reauth); }
function configuredCount() {
  return Object.values(S?.connectors || {}).reduce((n, c) => n + c.accounts.length, 0);
}
function furthestStep() {
  if (!connectedLogins().length) return 1;
  if (!configuredCount()) return 2;
  if (!S.last_run || !S.last_run.finished_at) return 3;
  if (!S.claude_registered) return 4;
  return 5;
}
function stepDone(i) { return i < furthestStep(); }

// -------------------------------------------------------------- stepper
function renderStepper() {
  const max = furthestStep();
  $("stepper").innerHTML = STEPS.map((name, i) => {
    const done = stepDone(i);
    const item = `<button class="step-item ${i === step ? "active" : ""} ${done ? "done" : ""}"
            ${i > max ? "disabled" : ""} onclick="go(${i})">
      <span class="step-circle">${done ? "✓" : i + 1}</span>
      <span class="step-label">${esc(name)}</span></button>`;
    // the connector before step i is "passed" once step i itself is reached
    const line = i > 0 ? `<span class="step-line ${i <= step || stepDone(i) ? "passed" : ""}"></span>` : "";
    return line + item;
  }).join("");
  $("versionTag").textContent = "v" + (S?.version?.current || "");
  const b = $("updateBanner");
  if (S?.version?.update_available) {
    b.hidden = false;
    b.innerHTML = `Version ${esc(S.version.latest)} is available — <a href="${esc(S.version.download_url)}" target="_blank">download it</a> (you have ${esc(S.version.current)}).`;
  }
}

function go(i) {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  step = i;
  renderStepper();
  [welcome, google, accounts, sync, claude, done][i]();
  window.scrollTo(0, 0);
}

// -------------------------------------------------------------- 1 welcome
function welcome() {
  const client = {bundled: "You're all set — nothing else to configure.",
                  own: "This hub is using a custom Google connection.",
                  missing: "Something's missing. Please reinstall the app, or contact support."}[S.client_source];
  $("view").innerHTML = `
    <div class="card">
      <h1>Let's get your marketing data in one place.</h1>
      <p>Five short steps, about five minutes. You'll sign in to Google, pick the properties you
         care about, load the data, and connect Claude so you can ask questions in plain English.</p>
      <h2>Before you start</h2>
      <p class="${S.client_source === "missing" ? "err" : ""}">${esc(client)}</p>
      <p class="muted">Everything is stored in <code>${esc(S.home)}</code> on this computer. Nothing is uploaded anywhere.</p>
      <div class="actions"><button class="btn primary" onclick="go(1)">Get started →</button></div>
    </div>`;
}

// -------------------------------------------------------------- 2 google
function google() {
  const logins = S.identities.map(i => i.needs_reauth
    ? `<span class="pill warn" onclick="connectGoogle('${esc(i.identity)}')">${esc(i.identity)} — click to authorize</span>`
    : `<span class="pill">✓ ${esc(i.label)}
         <span class="x" title="sign in again (if Google says the login expired)" onclick="connectGoogle('${esc(i.identity)}')">↻</span>
         <span class="x" title="disconnect this Google account" onclick="disconnectGoogle('${esc(i.identity)}','${esc(i.label)}')">disconnect ✕</span></span>`).join("") || `<span class="muted">none yet</span>`;
  $("view").innerHTML = `
    <div class="card">
      <h1>Connect Google</h1>
      <p>Sign in with the Google account that can see your GA4 properties or Search Console sites.
         Read-only access — the tool can't change anything.</p>
      <p>Connected: ${logins}</p>
      <div class="actions">
        <button class="btn primary" onclick="connectGoogle()">${connectedLogins().length ? "+ Add another Google account" : "Sign in with Google"}</button>
        <span id="msg" class="muted"></span>
      </div>
      <div class="actions"><button class="btn" onclick="go(2)" ${connectedLogins().length ? "" : "disabled"}>Continue →</button></div>
    </div>`;
}

async function disconnectGoogle(identity, label) {
  const owned = Object.values(S.connectors).reduce((n, c) => n + c.accounts.filter(a => a.identity === identity).length, 0);
  const msg = `Disconnect ${label}?` + (owned ? `\n\n${owned} account(s) synced through this login will be removed from the sync list (their data stays in your database).` : "")
    + `\n\nTo also revoke access on Google's side, visit myaccount.google.com/permissions.`;
  if (!confirm(msg)) return;
  await api("/api/google/disconnect", {method: "POST", body: JSON.stringify({identity})});
  await refresh();
  google();
}

async function connectGoogle(identity) {
  $("msg").textContent = "A Google sign-in tab opened — finish there, then come back (you have a few minutes).";
  const r = await api("/api/google/connect", {method: "POST", body: JSON.stringify(identity ? {identity} : {})});
  if (r.error) { $("msg").innerHTML = `<span class="err">${esc(r.error)}</span>`; return; }
  const wait = r.identity;
  const t = setInterval(async () => {
    await refresh();
    const found = S.identities.find(i => i.identity === wait && !i.needs_reauth);
    if (found) { clearInterval(t); go(2); return; }
    if (S.login_errors[wait]) {
      clearInterval(t);
      google();
      $("msg").innerHTML = `<span class="err">${esc(S.login_errors[wait])}</span> — click the button to try again`;
    }
  }, 2000);
}

// ------------------------------------------------------------ 3 accounts
function accounts() {
  const logins = connectedLogins();
  if (!ident || !logins.some(l => l.identity === ident)) ident = logins[0]?.identity || null;
  $("view").innerHTML = `
    <div class="card">
      <h1>Choose what to sync</h1>
      <p class="muted">Pick a source, then the Google login it belongs to. Tick what you want and add it.</p>
      <div class="tabs" id="srcTabs"></div>
      <div class="tabs" id="loginTabs"></div>
      <input type="search" id="q" placeholder="Search by name…" oninput="renderList()">
      <div id="listMsg" class="muted"></div>
      <div class="accounts" id="list" hidden></div>
      <div class="actions">
        <button class="btn primary" id="addBtn" onclick="addSelected()" disabled>Add <span class="count" id="cnt">0</span> selected</button>
        <button class="btn" onclick="loadList(true)">Refresh list</button>
        <span id="addMsg"></span>
      </div>
      <h2>Currently syncing (<span id="confCount"></span>)</h2>
      <div id="configured"></div>
      <details class="adv"><summary>Advanced: Google Ads &amp; Meta Ads tokens</summary>
        <h2 style="font-size:1rem">Meta Ads</h2>
        <label>Access token</label><input type="password" id="metaToken">
        <label>Ad account id(s), comma-separated</label><input type="text" id="metaAccounts" placeholder="act_123, act_456">
        <button class="btn" onclick="saveMeta()">Save Meta Ads</button> <span id="metaMsg"></span>
        <h2 style="font-size:1rem">Google Ads</h2>
        <label>Developer token</label><input type="password" id="adsDevToken">
        <label>Customer id(s)</label><input type="text" id="adsCustomers" placeholder="123-456-7890">
        <label>Manager (MCC) id — optional</label><input type="text" id="adsLogin">
        <button class="btn" onclick="saveGoogleAds()">Save Google Ads</button> <span id="adsMsg"></span>
      </details>
      <div class="actions"><button class="btn primary" id="toSync" onclick="startSyncFlow()" ${configuredCount() ? "" : "disabled"}>Continue to sync →</button></div>
    </div>`;
  renderTabs(); renderConfigured();
  if (ident) loadList(false);
}

function renderTabs() {
  $("srcTabs").innerHTML = [["ga4", "GA4", "ga4.png"], ["gsc", "Search Console", "gsc.png"]].map(([id, l, icon]) =>
    `<button class="${id === src ? "active" : ""}" onclick="src='${id}';selected.clear();renderTabs();loadList(false)"><img class="src-icon" src="/static/icons/${icon}" alt="">${l}</button>`).join("");
  $("loginTabs").innerHTML = connectedLogins().map(l =>
    `<button class="${l.identity === ident ? "active" : ""}" onclick="ident='${esc(l.identity)}';selected.clear();renderTabs();loadList(false)">${esc(l.label)}</button>`).join("");
}

async function loadList(refreshList) {
  const req = ++lastReq;                      // stale responses are dropped below
  $("listMsg").innerHTML = `<span class="spin"></span> loading ${src === "ga4" ? "GA4 properties" : "Search Console sites"} (can take ~10s)…`;
  $("list").hidden = true;
  const r = await api(`/api/accounts?identity=${encodeURIComponent(ident)}&source=${src}&refresh=${refreshList ? 1 : 0}&request_id=${req}`);
  if (String(r.request_id) !== String(req)) return;   // a newer request superseded this one
  if (r.error) { $("listMsg").innerHTML = `<span class="err">${esc(r.error)}</span>`; return; }
  discovered = r.accounts; selected.clear();
  $("listMsg").textContent = discovered.length ? "" : "No accounts visible to this login.";
  $("list").hidden = !discovered.length;
  renderList();
}

function row(a, i) {
  let label = esc(a.name) + (a.id && a.id !== a.name ? ` <span class="muted">— ${esc(a.id)}</span>` : "");
  if (a.duplicate_name) {
    const act = a.active_recently === false ? '<span class="err">no data in last 30 days — likely the wrong one</span>'
             : a.active_recently === true ? '<span class="ok">has recent data</span>' : '<span class="muted">activity unknown</span>';
    label += ` <span class="err">⚠ another account has this name</span> (${act})`;
  }
  return a.configured ? `<label class="added">✓ ${label} <span class="muted">already added</span></label>`
    : `<label><input type="checkbox" data-i="${i}" ${selected.has(i) ? "checked" : ""} onchange="toggle(${i}, this.checked)"> ${label}</label>`;
}

function renderList() {
  const term = $("q").value.trim().toLowerCase();
  const rows = discovered.map((a, i) => [a, i]).filter(([a]) => !term || a.name.toLowerCase().includes(term) || a.id.toLowerCase().includes(term));
  if (!rows.length) { $("list").innerHTML = '<p class="muted">no matches</p>'; updateCount(); return; }
  if (src === "ga4") {
    const groups = {};
    rows.forEach(([a, i]) => (groups[a.parent || a.name] ||= []).push([a, i]));
    $("list").innerHTML = Object.entries(groups).map(([parent, rs]) => `
      <details ${term || Object.keys(groups).length === 1 ? "open" : ""}>
        <summary>${esc(parent)} <span class="muted">(${rs.length})</span>
          <span class="sel" onclick="event.preventDefault();selectGroup([${rs.filter(([a]) => !a.configured).map(([, i]) => i)}])">select all</span></summary>
        ${rs.map(([a, i]) => row(a, i)).join("")}</details>`).join("");
  } else {
    $("list").innerHTML = rows.map(([a, i]) => row(a, i)).join("");
  }
  updateCount();
}
function toggle(i, on) { on ? selected.add(i) : selected.delete(i); updateCount(); }
function selectGroup(ids) { ids.forEach(i => selected.add(i)); renderList(); }
function updateCount() { $("cnt").textContent = selected.size; $("addBtn").disabled = !selected.size; }

async function addSelected() {
  const ids = [...selected].map(i => discovered[i].id);
  $("addBtn").disabled = true;
  const r = await api("/api/accounts/add", {method: "POST", body: JSON.stringify({source: src, ids, identity: ident})});
  $("addMsg").innerHTML = r.error ? `<span class="err">${esc(r.error)}</span>` : `<span class="ok">added ${r.added.length} ✓</span>`;
  await refresh();
  discovered = discovered.map(a => ids.includes(a.id) ? {...a, configured: true} : a);
  selected.clear(); renderList(); renderConfigured();
  $("toSync").disabled = !configuredCount();
}

function renderConfigured() {
  const items = [];
  for (const [s, info] of Object.entries(S.connectors)) for (const a of info.accounts)
    items.push(`<span class="pill">${sourceIcon(s)}${esc(a.label)} <span class="x" title="stop syncing this account" onclick="removeAccount('${esc(s)}','${esc(a.id)}','${esc(a.label)}')">remove ✕</span></span>`);
  $("confCount").textContent = items.length;
  $("configured").innerHTML = items.join("") || '<span class="muted">nothing yet</span>';
}
async function removeAccount(s, id, label) {
  if (!confirm(`Stop syncing "${label}"?\n\nData already loaded stays in your database; it just won't refresh. You can add it back any time.`)) return;
  await api("/api/accounts/remove", {method: "POST", body: JSON.stringify({source: s, ids: [id]})});
  await refresh();
  discovered = discovered.map(a => a.id === id ? {...a, configured: false} : a);
  renderList(); renderConfigured(); $("toSync").disabled = !configuredCount();
}

async function saveMeta() {
  const accounts = $("metaAccounts").value.split(",").map(s => s.trim()).filter(Boolean);
  const r = await api("/api/connector/options", {method: "POST", body: JSON.stringify({source: "meta_ads",
    options: {access_token: $("metaToken").value.trim(), ad_account_ids: accounts}})});
  $("metaMsg").innerHTML = r.error ? `<span class="err">${esc(r.error)}</span>` : '<span class="ok">saved ✓</span>';
}
async function saveGoogleAds() {
  const customers = $("adsCustomers").value.split(",").map(s => s.trim()).filter(Boolean);
  const r = await api("/api/connector/options", {method: "POST", body: JSON.stringify({source: "google_ads",
    options: {developer_token: $("adsDevToken").value.trim(), customer_ids: customers, login_customer_id: $("adsLogin").value.trim()}})});
  $("adsMsg").innerHTML = r.error ? `<span class="err">${esc(r.error)}</span>` : '<span class="ok">saved ✓</span>';
}

// ---------------------------------------------------------------- 4 sync
async function startSyncFlow() {
  try {
    const result = await api("/api/sync", {method: "POST"});
    if (result.error) { alert(result.error); return; }
    go(3);
  } catch (error) { alert(`Unable to start sync: ${error.message}`); }
}

function sync() {
  $("view").innerHTML = `
    <div class="card">
      <h1>Loading your data</h1>
      <p class="muted">The last 30 days for every account. You can close this tab — the sync keeps running;
         reopen the setup any time to see where it got to.</p>
      <div class="progress"><div id="bar" style="width:0%"></div></div>
      <div id="syncSummary" class="muted"></div>
      <table class="sync" id="syncTable"></table>
      <div class="actions">
        <button class="btn" onclick="startSyncFlow()">Run again</button>
        <button class="btn primary" id="toClaude" onclick="go(4)" disabled>Continue →</button>
      </div>
    </div>`;
  let polling = false;
  const tick = async () => {
    if (polling || step !== 3) return;
    polling = true;
    try {
    const s = await api("/api/sync/status");
    if (step !== 3) return;
    const accts = s.run?.accounts || [];
    const doneN = accts.filter(a => a.status === "done" || a.status === "error").length;
    $("bar").style.width = accts.length ? `${Math.round(100 * doneN / accts.length)}%` : "0%";
    $("syncSummary").textContent = s.error || (!accts.length ?
      (s.in_progress ? "starting…" : s.run ? "Sync finished — no accounts configured." : "No sync is running. Choose Run again to start.") :
      s.in_progress ? `${doneN} of ${accts.length} accounts done` : `finished — ${accts.reduce((n, a) => n + (a.rows || 0), 0).toLocaleString()} rows loaded`);
    $("syncTable").innerHTML = accts.map(a => `<tr>
      <td>${a.status === "done" ? '<span class="ok">✓</span>' : a.status === "error" ? '<span class="err">✗</span>' : a.status === "running" ? '<span class="spin"></span>' : '<span class="muted">·</span>'}</td>
      <td>${sourceIcon(a.source)}${esc(a.label)}</td>
      <td class="muted">${a.status === "error" ? `<span class="err">${esc(a.error)}</span>` : a.rows ? a.rows.toLocaleString() + " rows" : a.status === "done" ? "no data in the last 30 days" : a.status}</td></tr>`).join("");
    if (!s.in_progress && s.run) {
      clearInterval(pollTimer); pollTimer = null;
      $("toClaude").disabled = false;
      await refresh();
    }
    } catch (error) {
      if (step === 3) $("syncSummary").textContent = `Unable to read sync status: ${error.message}`;
    } finally { polling = false; }
  };
  tick(); pollTimer = setInterval(tick, 3000);
}

// -------------------------------------------------------------- 5 claude
async function claude() {
  const d = await api("/api/claude/detect");
  const targets = d.targets.map(t => `<p>${esc(t.label)} <span class="muted">${esc(t.path)}</span>
      ${t.registered ? '<span class="ok">✓ connected</span>' : `<button class="btn primary" onclick="connectClaude('${esc(t.id)}')">Connect</button>`}</p>`).join("");
  $("view").innerHTML = `
    <div class="card">
      <h1>Connect Claude</h1>
      <p>This registers the hub with Claude so you can ask questions about your data.</p>
      ${targets || `<p class="err">Claude Desktop wasn't found on this computer.</p>
        <p>Install it from <a href="https://claude.ai/download" target="_blank">claude.ai/download</a>, then come back and click <b>Check again</b>.</p>
        <div class="actions"><button class="btn" onclick="claude()">Check again</button></div>`}
      <div id="claudeMsg"></div>
      <details class="adv"><summary>Manual setup (paste into Claude Desktop → Settings → Developer → Edit Config, inside "mcpServers")</summary>
        <pre id="snippet">${esc(d.snippet)}</pre>
        <button class="btn" onclick="navigator.clipboard.writeText($('snippet').textContent);$('claudeMsg').innerHTML='<span class=ok>copied ✓</span>'">Copy</button>
      </details>
      <div class="actions"><button class="btn primary" onclick="go(5)">${S.claude_registered ? "Continue →" : "Skip for now →"}</button></div>
    </div>`;
}
async function connectClaude(target) {
  const r = await api("/api/claude/connect", {method: "POST", body: JSON.stringify({target})});
  if (r.error) { $("claudeMsg").innerHTML = `<span class="err">${esc(r.error)}</span>`; return; }
  await refresh();
  await claude();
  $("claudeMsg").innerHTML = `<p class="ok">Connected ✓ — now <b>fully quit Claude</b> (system tray → Quit, not just close the window) and reopen it.</p>
    <p>Then try asking: <i>"How did my organic traffic do last week?"</i>
    <button class="btn" onclick="navigator.clipboard.writeText('How did my organic traffic do last week?')">Copy question</button></p>`;
}

// ----------------------------------------------------------------- 6 done
async function done() {
  const run = S.last_run;
  const rows = (run?.accounts || []).reduce((n, a) => n + (a.rows || 0), 0);
  const when = run?.finished_at ? new Date(run.finished_at).toLocaleString() : "never";
  const failed = (run?.accounts || []).filter(a => a.status === "error").length;
  $("view").innerHTML = `
    <div class="card">
      <h1>Marketing Data Hub</h1>
      <p class="muted">This is your home page — it opens from the desktop icon. Everything below is one click.</p>
      <div class="summary-grid">
        <div><b>${configuredCount()}</b>accounts syncing</div>
        <div><b>${rows.toLocaleString()}</b>rows in last sync</div>
        <div><b>${S.claude_registered ? "✓" : "–"}</b>Claude connected</div>
        <div><b id="schedTxt">…</b>daily sync</div>
      </div>
      <p class="muted">Last sync: ${esc(when)}${failed ? ` — <span class="err">${failed} account(s) failed</span>` : ""}.
         Data refreshes every morning at 6:00 (the laptop just needs to be on at some point that day).</p>
      <div class="actions">
        <button class="btn primary" onclick="window.open('/dashboard','_blank')">Open dashboard ↗</button>
        <button class="btn" onclick="go(2)">Add / remove accounts</button>
        <button class="btn" onclick="startSyncFlow()">Sync now</button>
        <button class="btn" onclick="go(1)">Google logins</button>
        <button class="btn" onclick="go(4)">Claude</button>
      </div>
      <p class="muted" id="shortcutMsg" style="margin-top:1rem"></p>
      <div class="actions"><button class="btn" onclick="finish()">Close</button></div>
    </div>`;
  const r = await api("/api/schedule", {method: "POST"});
  $("schedTxt").textContent = r.installed ? "06:00" : (r.cron_line ? "manual (cron)" : "not set");
  if (r.error) $("schedTxt").title = r.error;
  const sc = await api("/api/shortcut", {method: "POST"});
  $("shortcutMsg").innerHTML = sc.created?.length
    ? `A <b>Marketing Data Hub</b> icon is on your Desktop and Start Menu — use it to come back here.`
    : sc.error ? `<span class="err">${esc(sc.error)}</span>` : esc(sc.hint || "");
}
async function finish() {
  await api("/api/shutdown", {method: "POST"});
  document.body.innerHTML = '<div class="view"><div class="card"><h1>Closed ✓</h1><p>You can close this tab. Run <b>Marketing Data Hub</b> from the Start menu (or <code>hub setup</code>) any time.</p></div></div>';
}

// ---------------------------------------------------------------- boot
// a brand-new hub starts on Welcome; anything already connected resumes where it
// left off; "#accounts" (from the dashboard's links) jumps straight to the account list
(async () => {
  await refresh();
  if (location.hash === "#accounts" && connectedLogins().length) { history.replaceState(null, "", "/"); go(2); return; }
  go(connectedLogins().length ? furthestStep() : 0);
})();
