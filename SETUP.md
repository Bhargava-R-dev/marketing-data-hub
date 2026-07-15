# Setup Guide — Marketing Data Hub

This is a personal marketing-analytics pipeline: it pulls your Google
Analytics 4, Search Console (and optionally YouTube, Google Ads, Meta Ads)
data into a local database you can query from an API, scheduled CSV exports,
or Claude via MCP. Everything runs on your own machine; nothing is uploaded
anywhere.

Budget ~30 minutes for first-time setup. The one-time Google Cloud step is
the only fiddly part — follow it carefully and the rest is copy-paste.

---

## Shortcut: teammates on the SAME Google account

If a colleague works on the **same** Google/agency login and you just want them
running fast, you can skip the entire Google Cloud setup (steps 2–5 below) by
**copying your working folder to their machine** over a trusted internal channel
(USB drive or internal network share — *not* email, cloud drives, or anything
public; the folder contains a live access token). Then they only need:

1. Install Python 3.11+.
2. Copy the whole `data collection` folder to a **short path** (e.g.
   `C:\dev\marketing-data-hub` — deep paths break the install on Windows).
3. `cd` in and run `python -m pip install -e ".[dev]"`.
4. `hub status` — it should show your existing data immediately (paths in
   config.yaml are relative, so the copy works with no edits).

That's it — the copied `secrets/`, `config.yaml`, and database come along, so no
Cloud project, no OAuth, no reconfiguration. They can then run `hub serve`,
`hub export`, or register the MCP server as below.

**Know the trade-offs of the copy shortcut:**
- It shares **one** access token across machines. If anyone revokes it (or the
  account owner removes app access), everyone's sync stops at once.
- There's no per-person audit — all activity looks like the one shared account.
- Each machine's daily sync hits Google independently; fine for a few people,
  but don't copy to a whole department. For that, give people their own Google
  Cloud credentials (the full setup below).
- Copy the **database** only *after* any in-progress backfill finishes, or just
  delete `data/` on their copy and let them `hub sync` / `hub backfill` fresh.

For anyone **not** on your Google account, they must do the full setup:

---

## What you need first

- **Python 3.11 or newer** (`python --version` to check).
- **A Google account that already has access to some GA4 properties and/or
  Search Console sites.** This tool reads whatever Google grants your login —
  it can't access data you don't already have. If you can see it in the GA4
  or Search Console web UI, you can pull it here.

---

## 1. Get the code & install

```bash
git clone <the repo URL you were given>
cd marketing-data-hub
python -m pip install -e ".[dev]"
```

Optional extras, only if you'll use those connectors:
`python -m pip install -e ".[googleads]"` / `".[meta]"`.

## 2. Create your Google Cloud OAuth credentials (one time)

This is what lets the tool sign in as you and read your data.

1. Go to <https://console.cloud.google.com/> → create a new project (any name).
2. **APIs & Services → Enable APIs & Services** → enable each of:
   - **Google Analytics Data API** (for GA4)
   - **Google Analytics Admin API** (so `hub accounts` can list your properties)
   - **Google Search Console API**
   - **YouTube Analytics API** (only if you'll use YouTube)
3. **APIs & Services → OAuth consent screen**:
   - User type: **External**.
   - Fill the required name/email fields.
   - **⚠️ Important — token expiry:** while the app is in **"Testing"** status,
     your login token expires **every 7 days** and the sync will silently
     start failing. Two fixes:
     - **Add yourself as a Test user** (Audience → Test users) *and* click
       **"Publish app" → Production** to stop the 7-day expiry. Publishing a
       personal app used only by you does not require Google verification.
4. **APIs & Services → Credentials → Create credentials → OAuth client ID**:
   - Application type: **Desktop app**.
   - Download the JSON.
5. Put that file at **`secrets/google_client.json`** in the repo folder.
   (Create the `secrets/` folder if it isn't there.)

## 3. Configure

```bash
cp config.yaml.example config.yaml     # Windows: copy config.yaml.example config.yaml
cp .env.example .env
```

- In **`.env`**, set `HUB_API_KEY` to any random string (used only to protect
  the local query API).
- Leave `config.yaml` mostly as-is for now — you'll fill in accounts in step 5.

## 4. Authorize

```bash
hub doctor
```

The first run opens a browser to sign in and grant access. After that all
checks should go green. If you see auth errors later, delete
`secrets/google_token.json` and run `hub doctor` again to re-authorize.

## 5. Pick your accounts (the easy way)

```bash
hub accounts            # lists every GA4 property & GSC site your login can see
hub accounts --add      # shows a numbered list; type e.g. "3,7,12" to add them
```

This writes your chosen properties/sites into `config.yaml` with friendly
labels filled in automatically. You can also add them by hand in `config.yaml`
following the examples there.

**If you report on branded vs non-branded search:** add a `brand_terms` block
per site in `config.yaml` (see the example file) — queries containing any of
those terms get tagged `branded` at sync time.

## 6. Load data

```bash
hub sync all                              # pulls the rolling 30-day window
hub backfill ga4 --from 2024-06-01        # optional: load history in chunks
hub backfill gsc --from 2025-03-15        # GSC only keeps ~16 months, so do this soon
hub status                                # row counts + last sync per source
```

## 7. Use it

- **Query API + scheduler:** `hub serve` → <http://127.0.0.1:8000> (send your
  `HUB_API_KEY` as the `X-API-Key` header). See README for endpoints.
- **CSV exports:** `hub export all` → writes to `exports/`.
- **Claude (MCP):**
  `claude mcp add marketing-hub -- python -m hub.cli mcp --config <absolute-path>/config.yaml`
  then ask Claude about your data. Use an **absolute** path to config.yaml.

## 8. Automate the daily sync (optional)

- **Windows:** Task Scheduler → new daily task → action runs
  `scripts\sync_daily.bat`. The script finds the repo automatically. If the
  task can't find Python, set a `PYTHON` env var to the full python.exe path.
- **macOS/Linux:** `crontab -e` →
  `0 6 * * * /full/path/to/marketing-data-hub/scripts/sync_daily.sh`

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Sync fails after ~7 days | OAuth app still in "Testing" — publish to Production (step 2.3). |
| `AuthError` / 403 | Delete `secrets/google_token.json`, run `hub doctor` to re-consent. |
| `hub accounts` shows nothing | Your Google login has no GA4/GSC access, or the Admin API isn't enabled (step 2.2). |
| "database is busy" from MCP | A sync is running (it holds the write lock). Wait / check `sync_status`. |
| MCP tools not showing in Claude | Fully quit and reopen the Claude app after registering the server. |
| `pip install` fails with a long-path / `No such file or directory` error on Windows | The `google-analytics-data` package nests files deeply and can exceed Windows' 260-char path limit. Clone into a **short** path (e.g. `C:\dev\marketing-data-hub`, not a deep `Downloads\...` folder), or enable Long Path support: <https://pip.pypa.io/warnings/enable-long-paths>. |

## Notes

- Run **`hub serve` OR `hub mcp`, not both at once** — the database allows one
  writer at a time.
- **Never commit or send anyone** `secrets/`, `.env`, `config.yaml`, or the
  `data/` database — they contain your credentials and your clients' data.
  These are gitignored, so a normal `git push` is safe; just don't zip the
  whole folder and email it.
