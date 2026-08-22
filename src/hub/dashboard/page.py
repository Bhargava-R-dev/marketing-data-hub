"""The dashboard page: what's in the hub, grouped by source. Read-only,
no auth token — same trust model as `hub status` on the CLI."""
from __future__ import annotations

_PAGE = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Marketing Data Hub - Dashboard</title>
<style>
  :root { color-scheme: light dark; }
  body { font-family: system-ui, sans-serif; max-width: 900px; margin: 2rem auto;
         padding: 0 1rem; line-height: 1.45; }
  h1 { font-size: 1.5rem; }
  .group { border: 1px solid #8884; border-radius: 10px; padding: 1rem 1.2rem;
           margin: 1rem 0; }
  .group-header { display: flex; align-items: baseline; justify-content: space-between;
                  flex-wrap: wrap; gap: .4rem; }
  .group-header h2 { font-size: 1.05rem; margin: 0; text-transform: uppercase;
                     letter-spacing: .04em; }
  .sync-status { font-size: .85rem; }
  .ok { color: #16a34a; } .err { color: #dc2626; } .muted { opacity: .65; }
  table { width: 100%; border-collapse: collapse; margin-top: .7rem; font-size: .92rem; }
  th, td { text-align: left; padding: .35rem .5rem; border-bottom: 1px solid #8882; }
  th { font-weight: 600; opacity: .75; font-size: .82rem; text-transform: uppercase; }
  .empty { text-align: center; opacity: .6; padding: 3rem 1rem; }
  #refreshMsg { font-size: .85rem; opacity: .6; }
</style>
</head>
<body>
<h1>Your Data</h1>
<p class="muted">What's synced into your hub right now — refreshes automatically.
 <span id="refreshMsg"></span></p>
<div id="content"><p class="muted">loading&hellip;</p></div>

<script>
function esc(s) { return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;"); }
function fmtNum(n) { return (n || 0).toLocaleString(); }

function syncBadge(sync) {
  if (!sync) return '<span class="muted">never synced</span>';
  if (sync.status === "success")
    return `<span class="ok">✓ synced</span> <span class="muted">${esc(sync.finished_at || "")}</span>`;
  if (sync.status === "running")
    return '<span class="muted">⏳ syncing…</span>';
  return `<span class="err">✗ ${esc(sync.error || sync.status)}</span>`;
}

function freshnessBadge(f) {
  if (!f) return "";
  if (f.status === "no_data") return '<span class="muted">no data</span>';
  if (f.status === "current") return '<span class="ok">&check; current</span>';
  return `<span class="err">&#9888; ${f.days_behind} day(s) behind expected</span>`;
}

function gapsBadge(n) {
  if (!n) return '<span class="ok">&check; none</span>';
  return `<span class="err">&#9888; ${n} day(s) missing</span>`;
}

function render(data) {
  const el = document.getElementById("content");
  if (data.busy) {
    el.innerHTML = '<p class="muted">database is busy (a sync is running) — retrying…</p>';
    return;
  }
  if (!data.groups.length) {
    el.innerHTML = '<div class="empty">No data yet. Run <code>hub setup</code> to connect accounts and sync.</div>';
    return;
  }
  el.innerHTML = data.groups.map(g => `
    <div class="group">
      <div class="group-header">
        <h2>${esc(g.source)}</h2>
        <span class="sync-status">${syncBadge(g.last_sync)}</span>
      </div>
      ${g.accounts.length ? `
      <table>
        <tr><th>Brand</th><th>Google login</th><th>Date range</th><th>Rows</th><th>Freshness</th><th>Gaps</th></tr>
        ${g.accounts.map(a => `
          <tr>
            <td>${esc(a.account_name)}</td>
            <td class="muted">${esc(a.identity)}</td>
            <td>${esc(a.first_date || "—")} &rarr; ${esc(a.latest_date || "—")}</td>
            <td>${fmtNum(a.rows)}</td>
            <td>${freshnessBadge(a.freshness)}</td>
            <td>${gapsBadge(a.gap_days)}</td>
          </tr>`).join("")}
      </table>` : '<p class="muted">no accounts configured for this source yet</p>'}
    </div>`).join("");
}

async function refresh() {
  try {
    const r = await fetch("/api/dashboard-data");
    render(await r.json());
    document.getElementById("refreshMsg").textContent =
      "last checked " + new Date().toLocaleTimeString();
  } catch (e) {
    document.getElementById("refreshMsg").textContent = "refresh failed - retrying…";
  }
}
refresh();
setInterval(refresh, 15000);
</script>
</body>
</html>
"""


def render_dashboard_page() -> str:
    return _PAGE
