/* Marketing Data Hub setup wizard v3 - vanilla JS, no build step. */
const H = {"Content-Type": "application/json", "X-Setup-Token": TOKEN};
const STEPS = ["Welcome", "Connect Google", "Choose accounts", "Sync", "Connect Claude", "Done"];
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");

async function api(path, opts) {
  const r = await fetch(path, Object.assign({headers: H}, opts || {}));
  return r.json();
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
  $("stepper").innerHTML = STEPS.map((name, i) => `
    <button class="${i === step ? "active" : ""} ${stepDone(i) ? "done" : ""}"
            ${i > max ? "disabled" : ""} onclick="go(${i})">
      <span class="n">${stepDone(i) ? "✓" : i + 1}</span>${name}</button>`).join("");
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
  const client = {bundled: "Signed in through Growth by Bhargava's Google app — nothing to configure.",
                  own: "Using your own Google client file from the secrets folder.",
                  missing: "No Google sign-in file found — reinstall, or add your own google_client.json."}[S.client_source];
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
    : `<span class="pill">✓ ${esc(i.label)} <span class="x" title="sign in again (if Google says the login expired)" onclick="connectGoogle('${esc(i.identity)}')">↻</span></span>`).join("") || `<span class="muted">none yet</span>`;
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
  $("srcTabs").innerHTML = [["ga4", "GA4"], ["gsc", "Search Console"]].map(([id, l]) =>
    `<button class="${id === src ? "active" : ""}" onclick="src='${id}';selected.clear();renderTabs();loadList(false)">${l}</button>`).join("");
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
    items.push(`<span class="pill">${esc(s === "ga4" ? "GA4" : s === "gsc" ? "GSC" : s)}: ${esc(a.label)} <span class="x" title="remove" onclick="removeAccount('${esc(s)}','${esc(a.id)}')">✕</span></span>`);
  $("confCount").textContent = items.length;
  $("configured").innerHTML = items.join("") || '<span class="muted">nothing yet</span>';
}
async function removeAccount(s, id) {
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
async function startSyncFlow() { await api("/api/sync", {method: "POST"}); go(3); }

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
  const tick = async () => {
    const s = await api("/api/sync/status");
    const accts = s.run?.accounts || [];
    const doneN = accts.filter(a => a.status === "done" || a.status === "error").length;
    $("bar").style.width = accts.length ? `${Math.round(100 * doneN / accts.length)}%` : "0%";
    $("syncSummary").textContent = !accts.length ? "starting…" :
      s.in_progress ? `${doneN} of ${accts.length} accounts done` : `finished — ${accts.reduce((n, a) => n + (a.rows || 0), 0).toLocaleString()} rows loaded`;
    $("syncTable").innerHTML = accts.map(a => `<tr>
      <td>${a.status === "done" ? '<span class="ok">✓</span>' : a.status === "error" ? '<span class="err">✗</span>' : a.status === "running" ? '<span class="spin"></span>' : '<span class="muted">·</span>'}</td>
      <td>${esc(a.label)} <span class="muted">${esc(a.source.toUpperCase())}</span></td>
      <td class="muted">${a.status === "error" ? `<span class="err">${esc(a.error)}</span>` : a.rows ? a.rows.toLocaleString() + " rows" : a.status}</td></tr>`).join("");
    if (!s.in_progress && accts.length) {
      clearInterval(pollTimer); pollTimer = null;
      $("toClaude").disabled = false;
      await refresh();
    }
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
  const rows = (S.last_run?.accounts || []).reduce((n, a) => n + (a.rows || 0), 0);
  $("view").innerHTML = `
    <div class="card">
      <h1>You're all set ✓</h1>
      <div class="summary-grid">
        <div><b>${configuredCount()}</b>accounts syncing</div>
        <div><b>${rows.toLocaleString()}</b>rows loaded</div>
        <div><b>${S.claude_registered ? "✓" : "–"}</b>Claude connected</div>
        <div><b id="schedTxt">…</b>daily sync</div>
      </div>
      <p class="muted">Your data refreshes every morning at 6:00 (the laptop just needs to be on at some point that day).
         Run the setup again any time to add accounts or check progress.</p>
      <div class="actions">
        <button class="btn primary" onclick="window.open('/dashboard','_blank')">Open dashboard ↗</button>
        <button class="btn" onclick="go(2)">Add more accounts</button>
        <button class="btn" onclick="finish()">Close setup</button>
      </div>
    </div>`;
  const r = await api("/api/schedule", {method: "POST"});
  $("schedTxt").textContent = r.installed ? "06:00" : (r.cron_line ? "manual (cron)" : "not set");
  if (r.error) $("schedTxt").title = r.error;
}
async function finish() {
  await api("/api/shutdown", {method: "POST"});
  document.body.innerHTML = '<div class="view"><div class="card"><h1>Closed ✓</h1><p>You can close this tab. Run <b>Marketing Data Hub</b> from the Start menu (or <code>hub setup</code>) any time.</p></div></div>';
}

// ---------------------------------------------------------------- boot
// a brand-new hub starts on Welcome; anything already connected resumes where it left off
(async () => { await refresh(); go(connectedLogins().length ? furthestStep() : 0); })();
