# Public Distribution + Setup Wizard v3 — Design

## Goal

Turn Marketing Data Hub from a share-with-friends tool into something strangers
can install from growthbybhargava.com and get running without the author
present. Everything still runs on the user's own machine; the author hosts
nothing and pays for no infrastructure.

## Decisions (from user conversation, 2026-09-14)

- **No hosting.** Distribution = website landing page + downloadable installer
  + PyPI. Data, tokens, and sync all stay on the user's device.
- **Shared Google OAuth client.** The author's `google_client.json` is bundled
  in both the installer and the PyPI wheel (Google treats Desktop-app client
  secrets as non-confidential; gcloud/rclone do the same). Users who want their
  own Google project drop their own file in `secrets/`, which overrides the
  bundled one.
- **Google app verification** is required (removes the "unverified app" screen
  and the 100-user cap). Needs homepage, privacy policy, and terms on
  growthbybhargava.com plus a screencast. Started first because of Google's
  1–4 week lead time.
- **Two audiences, one wizard**: non-technical users get a Windows `.exe`;
  semi-technical users run `pip install marketing-data-hub && hub setup`.
  Both land in the same browser wizard.
- **Windows now, Mac later.**
- **Wizard becomes a guided multi-step flow** — reverses the 2026-08-03
  single-page decision. That decision predates real users; real users reported
  "no clue what is syncing" and poor overall UX, which a step flow with
  progress directly addresses.
- **Per-user home directory** replaces "current working folder" as the default
  location, eliminating the run-in-wrong-folder footgun.

## Observed onboarding failures this design fixes

1. Selecting many accounts is slow / errors — `add` re-discovers all
   properties and blocks.
2. GA4 properties appear under the Search Console tab — a slow GA4 response
   returns after the user switched tabs and overwrites the GSC list.
3. No visibility into what is syncing, what isn't, or the status — status is
   per-source only and lost on page reload.
4. Installing the local MCP fails — the wizard only shows a JSON snippet and
   expects the user to locate and edit Claude's config by hand.
5. Overall UX: one long page, no sense of progress, no "done" state.

## Sub-project 1 — Website + Google verification

Repo: `Bhargava-Website/bhargava-next` (Next.js, auto-deploys to Vercel).

New routes, styled with the existing tokens/CSS:
- `/tools/marketing-data-hub` — what it is; privacy pitch ("runs on your
  machine, your data never reaches us"); *Download for Windows* button linking
  to the latest GitHub Release asset; the `pip` snippet; link to GUIDE;
  "Advanced: use your own Google project" section (content moved from
  SETUP.md step 2).
- `/privacy` — states: read-only access to GA4 / Search Console; all data and
  tokens stored only on the user's device; nothing transmitted to the author;
  the Google API Services User Data Policy "Limited Use" disclosure; how to
  revoke access (myaccount.google.com/permissions) and delete local data.
- `/terms` — MIT-licensed software provided as-is; no warranty; no data
  processing by the author.
- `sitemap.ts` updated with the three routes.

Google Cloud console (user performs; a checklist with exact copy is delivered):
- OAuth consent screen: app name "Marketing Data Hub", logo, homepage
  `https://growthbybhargava.com/tools/marketing-data-hub`, privacy
  `https://growthbybhargava.com/privacy`, terms
  `https://growthbybhargava.com/terms`, authorized domain
  `growthbybhargava.com`.
- Scopes reduced to `analytics.readonly`, `webmasters.readonly`,
  `userinfo.email`. The YouTube scope is removed from the default
  `GOOGLE_SCOPES` (opt-in via config later); the youtube connector stays in
  the codebase but is not offered by the wizard.
- Publish to production; submit for verification with a ~2 minute screencast
  of sign-in → account picking → data shown locally.

## Sub-project 2 — Wizard v3

### Paths and bundled client

- New module `hub.core.paths`:
  - `default_home()` → `%LOCALAPPDATA%\MarketingDataHub` on Windows,
    `~/.marketing-data-hub` elsewhere. `HUB_HOME` env var overrides.
  - Resolution order for the config: explicit `--config` → `./config.yaml`
    if present (keeps the author's existing hub working unchanged) →
    `<home>/config.yaml` (created on first `hub setup`).
  - `config.yaml` written by the wizard uses paths relative to home.
- Bundled client: `src/hub/resources/google_client.json` (package data).
  `google_auth` looks for `<secrets_dir>/google_client.json` first, then the
  bundled file. The wizard's Welcome step shows which one is in use.
- `.gitignore` keeps `secrets/` ignored; the bundled file lives under
  `src/hub/resources/` and is committed deliberately.

### Backend (`src/hub/setup_wizard/app.py`)

- **Discovery cache**: `GET /api/accounts?identity=&source=` caches results in
  memory keyed by (identity, source) for the wizard process lifetime;
  `?refresh=1` bypasses. Response includes `request_id` echoed from the
  query so the front end can discard stale responses.
- **Add/remove**: `POST /api/accounts/add` validates against the cache (no
  re-discovery) and returns immediately. New `POST /api/accounts/remove`
  `{source, ids}` removes accounts from `config.yaml` (via a new
  `remove_accounts` in `hub.core.accounts`).
- **Sync progress file**: `hub.core.sync` writes
  `<home>/logs/sync_progress.json` — `{run_id, started_at, finished_at,
  accounts: [{source, account_id, label, identity, status, rows, error,
  started_at, finished_at}]}` — updated after each account. Written
  atomically (temp file + rename). `GET /api/sync/status` returns this file
  (falls back to the existing `sync_runs` query when absent). Dashboard
  reads the same file for "last sync" per account.
- **Claude connect**: `GET /api/claude/detect` returns candidates:
  Claude Desktop config paths that exist (`%LOCALAPPDATA%\Packages\Claude_*\
  LocalCache\Roaming\Claude\claude_desktop_config.json` and
  `%APPDATA%\Claude\claude_desktop_config.json`; macOS
  `~/Library/Application Support/Claude/`), whether the `claude` CLI is on
  PATH, and whether the hub is already registered. `POST /api/claude/connect`
  `{target}`: backs up the file to `<name>.bak-<timestamp>`, merges
  `mcpServers["marketing-hub"]` — command is `hub.exe` (frozen build) or
  `sys.executable -m hub.cli` (pip) with `mcp --config <abs path>` — preserves
  every other key, returns the path written. For the CLI target it runs
  `claude mcp add marketing-hub -- <cmd>`.
- **Version**: `GET /api/version` → `{current, latest, download_url}`; latest
  fetched once from the GitHub Releases API with a 3 s timeout, `null` on
  failure.
- **Scheduled sync**: new CLI command `hub schedule` registers/updates the
  daily 6am task (`schtasks` on Windows with StartWhenAvailable +
  AllowStartIfOnBatteries; prints a cron line elsewhere), running
  `hub sync all --config <path>`. `POST /api/schedule` calls the same
  function so pip users get the automation from the wizard's Done step and
  the installer gets it from its post-install task.
- Existing per-run token guard, Google login threading, and shutdown stay.

### Frontend

`page.py` is replaced by `src/hub/setup_wizard/static/{index.html, app.js,
style.css}` served via FastAPI `StaticFiles`; the run token and config path
are injected into `index.html` at serve time as before. Vanilla JS, no build
step.

Steps (stepper at top; sidebar lets the user jump back to completed steps):

1. **Welcome** — what will happen, estimated 5 minutes, which Google client
   is in use, data location. *Get started*.
2. **Connect Google** — one large *Sign in with Google* button; connected
   emails listed with ✓; *Add another account*; errors shown inline with
   *Try again*. Auto-advances when ≥1 login is connected.
3. **Choose accounts** — source tabs (GA4 / Search Console) and login tabs
   retained; search box; groups with *select all*; live "N selected" count;
   *Add N accounts* applies instantly. "Currently syncing" list with ✕ to
   remove. *Refresh list* button. Every list render checks the response's
   `request_id` against the latest issued one.
4. **Syncing** — starts automatically on entering the step (button to
   re-run). One row per account: spinner / ✓ rows / ✗ error; overall progress
   bar and elapsed time. "You can close this tab — sync continues" note.
   Re-opening the wizard mid-sync returns here with live state from the
   progress file.
5. **Connect Claude** — shows detected targets ("Claude Desktop found") with
   one *Connect* button each; on success: "Fully quit Claude (system tray →
   Quit) and reopen it" with a *Copy test question* button. Claude Code
   offered when the CLI is detected. Nothing detected → download link and the
   manual snippet in a collapsible.
6. **Done** — summary (accounts, rows, daily sync at 6am), *Open dashboard*,
   update banner when a newer release exists, *Close*.

On load the page computes the furthest incomplete step from `/api/state`
(logins → accounts → last sync → Claude registered) and lands there, so
re-running `hub setup` later opens on Done/dashboard rather than Welcome.

### Testing

- `tests/test_setup_wizard.py` (TestClient): discovery cache + refresh,
  `request_id` echo, add without re-discovery, remove, sync status from
  progress file, version endpoint offline behaviour, schedule endpoint on a
  temp home.
- New `tests/test_claude_connect.py`: merge into an existing config with other
  servers, both Windows paths, backup file created, frozen vs pip command.
- New `tests/test_paths.py`: home resolution order, `HUB_HOME`, cwd override.
- Manual: full wizard run-through in the browser on this machine against the
  author's live hub (cwd override keeps it untouched) and against a fresh
  `HUB_HOME` temp folder.

## Sub-project 3 — Windows installer + release pipeline

- `packaging/hub.spec` — PyInstaller onedir build producing `hub.exe`
  (entry `hub.cli:app`); hidden imports for duckdb, google api clients,
  fastmcp, uvicorn collected via hooks; bundled `resources/` and `static/`.
- `packaging/installer.iss` — Inno Setup: installs to
  `%LOCALAPPDATA%\Programs\MarketingDataHub` (per-user, no admin prompt);
  Start Menu shortcut "Marketing Data Hub" → `hub.exe setup`; post-install
  task registers the 6am sync via `hub.exe schedule`; runs the wizard on
  finish; uninstaller removes the scheduled task and program files but leaves
  `%LOCALAPPDATA%\MarketingDataHub` (data) in place with a notice.
- `.github/workflows/release.yml` on tag `v*`: job 1 builds the wheel and
  publishes to PyPI (trusted publishing); job 2 (windows-latest) runs
  PyInstaller + Inno Setup and uploads `MarketingDataHub-Setup-<ver>.exe` to a
  GitHub Release. Version read from `pyproject.toml`; `hub --version` and the
  wizard's `/api/version` use `importlib.metadata`.
- The MCP entry written by the wizard for the frozen build points at
  `<install dir>\hub.exe mcp --config <home>\config.yaml`.

## Order of work

1. Website pages + verification checklist (external lead time).
2. Wizard v3 (paths → backend → frontend → tests).
3. Installer + release workflow; first tagged release; website download
   button goes live.

## Non-goals

- Hosted/multi-tenant version.
- macOS installer (pip path works on Mac already).
- Electron/Tauri shell, system tray.
- Google Ads / Meta Ads wizard steps beyond the existing token fields (moved
  into an "Advanced" collapsible on the Choose accounts step, unchanged).
- Dashboard redesign (only gains per-account last-sync from the progress
  file).
