from __future__ import annotations

import secrets
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime
from pathlib import Path

import duckdb
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from hub.core.config import load_config
from hub.core.progress import SyncProgress
from hub.dashboard import dashboard_router

STATIC_DIR = Path(__file__).resolve().parent / "static"


def _render_index(run_token: str, config_path: str) -> str:
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    return (html.replace("__RUN_TOKEN__", run_token)
                .replace("__CONFIG_PATH_DISPLAY__", config_path)
                .replace("__CONFIG_PATH__", config_path.replace("\\", "\\\\")))


def create_setup_app(config_path: str | Path) -> FastAPI:
    config_path = Path(config_path).resolve()
    home = config_path.parent
    progress_file = home / "logs" / "sync_progress.json"
    app = FastAPI(title="Marketing Data Hub Setup")
    app.include_router(dashboard_router(config_path))  # same-process "Open dashboard"
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    run_token = secrets.token_hex(16)
    login_threads: dict[str, threading.Thread] = {}
    login_errors: dict[str, str] = {}
    discovery_cache: dict[tuple[str, str], list[dict]] = {}
    state = {"shutdown": False}

    def cfg():
        return load_config(config_path)

    def check_token(request: Request) -> None:
        if request.headers.get("X-Setup-Token") != run_token:
            raise HTTPException(status_code=403, detail="bad setup token")

    # ---- page ----------------------------------------------------------
    @app.get("/", response_class=HTMLResponse)
    def page() -> str:
        return _render_index(run_token, str(config_path))

    # ---- read state ----------------------------------------------------
    @app.get("/api/state")
    def get_state(request: Request) -> dict:
        check_token(request)
        from hub.connectors.google_auth import (backfill_identity_labels, client_file_for,
                                                list_identities)
        from hub.core import version
        from hub.setup_wizard import claude_config

        c = cfg()
        labels = backfill_identity_labels(c.secrets_dir)  # never opens a browser
        identities = [{"identity": ident, "label": labels.get(ident),
                       "needs_reauth": ident not in labels}
                      for ident in list_identities(c.secrets_dir)]
        connectors = {}
        for source, settings in c.connectors.items():
            opts = settings.options
            ids = (opts.get("property_ids") or opts.get("site_urls")
                   or opts.get("customer_ids") or opts.get("ad_account_ids") or [])
            single = (opts.get("property_id") or opts.get("site_url")
                      or opts.get("customer_id") or opts.get("ad_account_id"))
            if single and str(single) not in [str(i) for i in ids]:
                ids = [*ids, single]
            connectors[source] = {
                "accounts": [{"id": str(i),
                              "label": opts.get("labels", {}).get(str(i), str(i)),
                              "identity": opts.get("identities", {}).get(str(i), "default")}
                             for i in ids],
                "activated": source not in ("google_ads", "meta_ads") or bool(
                    opts.get("developer_token") or opts.get("access_token")),
            }
        client = client_file_for(c.secrets_dir)
        client_source = ("missing" if client is None
                         else "own" if client.parent == Path(c.secrets_dir) else "bundled")
        latest = version.latest()
        current = version.current()
        detect = claude_config.detect(config_path)
        return {"identities": identities,
                "logins_pending": [n for n, t in login_threads.items() if t.is_alive()],
                "login_errors": dict(login_errors),
                "connectors": connectors,
                "config_path": str(config_path), "home": str(home),
                "client_source": client_source,
                "claude_registered": any(t["registered"] for t in detect["targets"]),
                "last_run": SyncProgress.read(progress_file),
                "version": {"current": current,
                            "latest": latest["version"] if latest else None,
                            "download_url": latest["url"] if latest else None,
                            "update_available": bool(latest and version.is_newer(
                                latest["version"], current))}}

    # ---- google login ---------------------------------------------------
    def _next_identity_slug(secrets_dir) -> str:
        """Auto-assign an internal slug — the user never names or sees this;
        the UI shows the fetched email instead (see /api/state)."""
        from hub.connectors.google_auth import list_identities

        existing = set(list_identities(secrets_dir)) | set(login_threads)
        if "default" not in existing:
            return "default"
        n = 2
        while f"account{n}" in existing:
            n += 1
        return f"account{n}"

    @app.post("/api/google/connect")
    def google_connect(request: Request, body: dict | None = None) -> dict:
        check_token(request)
        body = body or {}
        c = cfg()
        # 'identity' is accepted for backward compat / power users, but the
        # wizard UI itself never asks for one - it's auto-assigned
        identity = (body.get("identity") or "").strip() or _next_identity_slug(c.secrets_dir)
        if identity in login_threads and login_threads[identity].is_alive():
            return {"status": "already_running"}
        from hub.connectors.google_auth import client_file_for
        if client_file_for(c.secrets_dir) is None:
            return {"error": "No Google sign-in file found. Reinstall, or place your own "
                             f"google_client.json in {c.secrets_dir}"}

        login_errors.pop(identity, None)  # clear any previous failure on retry

        def run_login():
            from hub.connectors.google_auth import login, merge_duplicate_identity
            try:
                login(c.secrets_dir, identity=identity)
                # signing into an account that's already connected must not
                # produce a second, identical login in the picker
                merged = merge_duplicate_identity(c.secrets_dir, identity)
                if merged != identity:
                    from hub.core.accounts import remap_identity

                    remap_identity(config_path, identity, merged)
                    login_threads.pop(identity, None)
                    discovery_cache.clear()  # the refreshed token may see more
            except Exception as exc:  # noqa: BLE001 - surfaced via /api/state, not swallowed
                login_errors[identity] = str(exc)

        t = threading.Thread(target=run_login, daemon=True)
        t.start()
        login_threads[identity] = t
        return {"status": "started", "identity": identity,
                "note": "a Google sign-in tab opened - complete it there"}

    # ---- account discovery / add / remove --------------------------------
    def _discover(identity: str, source: str, refresh: bool) -> list[dict]:
        from hub.connectors.google_auth import get_credentials
        from hub.core.accounts import discover_all

        key = (identity, source)
        if refresh or key not in discovery_cache:
            # never interactive here: an expired token must surface as an error
            # the page can act on, not a browser tab opened by a background call
            creds = get_credentials(cfg().secrets_dir, identity=identity, interactive=False)
            discovery_cache[key] = discover_all(creds, source)
        return discovery_cache[key]

    @app.get("/api/accounts")
    def get_accounts(request: Request, identity: str = "default", source: str = "ga4",
                     refresh: bool = False, request_id: str = "") -> dict:
        check_token(request)
        try:
            from hub.connectors.google_auth import token_path_for
            from hub.core.accounts import annotate_configured

            if not token_path_for(cfg().secrets_dir, identity).exists():
                return {"request_id": request_id,
                        "error": f"identity {identity!r} is not connected yet"}
            accounts = annotate_configured(_discover(identity, source, refresh), cfg())
            return {"request_id": request_id, "source": source, "identity": identity,
                    "accounts": accounts}
        except Exception as exc:  # noqa: BLE001 - show readable errors in the page
            return {"request_id": request_id,
                    "error": f"{exc} {getattr(exc, 'hint', '')}".strip()}

    @app.post("/api/accounts/add")
    def post_accounts_add(request: Request, body: dict) -> dict:
        check_token(request)
        try:
            from hub.core.accounts import add_accounts

            source, identity = body["source"], body.get("identity") or "default"
            ids = [str(i) for i in body.get("ids", [])]
            c = cfg()
            visible = {a["id"]: a for a in _discover(identity, source, refresh=False)}
            unknown = [i for i in ids if i not in visible]
            if unknown:
                return {"error": f"not visible to this login: {unknown}"}
            added = add_accounts(config_path, source, [visible[i] for i in ids],
                                 identity=identity, secrets_dir=c.secrets_dir)
            return {"added": added}
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}

    @app.post("/api/accounts/remove")
    def post_accounts_remove(request: Request, body: dict) -> dict:
        check_token(request)
        from hub.core.accounts import remove_accounts

        return {"removed": remove_accounts(config_path, body["source"],
                                           [str(i) for i in body.get("ids", [])])}

    # ---- token-based connectors (meta / google ads) ----------------------
    @app.post("/api/connector/options")
    def post_connector_options(request: Request, body: dict) -> dict:
        check_token(request)
        try:
            from hub.core.accounts import set_connector_options

            source = body["source"]
            options = {k: v for k, v in body.get("options", {}).items()
                       if v not in (None, "", [])}
            set_connector_options(config_path, source, options)
            return {"saved": sorted(options)}
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}

    # ---- sync ------------------------------------------------------------
    def _sync_argv() -> tuple[str, list[str]]:
        # --unattended: a dead token must show up as an error row in the Sync
        # step, never as a surprise browser tab opened by a background process
        args = ["sync", "all", "--unattended", "--config", str(config_path)]
        if getattr(sys, "frozen", False):
            return sys.executable, args
        return sys.executable, ["-m", "hub.cli", *args]

    @app.post("/api/sync")
    def post_sync(request: Request) -> dict:
        check_token(request)
        log_path = home / "logs" / "setup_sync.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as log:
            log.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] setup wizard sync\n")
            log.flush()
            exe, args = _sync_argv()
            subprocess.Popen([exe, *args], stdout=log, stderr=subprocess.STDOUT,
                             stdin=subprocess.DEVNULL,
                             creationflags=(subprocess.CREATE_NO_WINDOW
                                            if sys.platform == "win32" else 0))
        return {"status": "started"}

    @app.get("/api/sync/status")
    def get_sync_status(request: Request) -> dict:
        check_token(request)
        run = SyncProgress.read(progress_file)
        if run is not None:
            return {"in_progress": run["finished_at"] is None, "run": run}
        # no progress file yet (never synced, or an older version): fall back
        c = cfg()
        if not Path(c.db_path).exists():
            return {"in_progress": False, "run": None}  # brand-new hub, nothing ran yet
        try:
            conn = duckdb.connect(c.db_path, read_only=True)
            rows = conn.execute(
                """SELECT source, status, rows_written, error_message FROM sync_runs
                   QUALIFY ROW_NUMBER() OVER (PARTITION BY source
                   ORDER BY started_at DESC) = 1""").fetchall()
            conn.close()
        except Exception:  # noqa: BLE001 - write lock held = sync in flight
            return {"in_progress": True, "run": None}
        running = any(r[1] == "running" for r in rows)
        return {"in_progress": running,
                "run": None if not rows else {
                    "started_at": None, "finished_at": None if running else "",
                    "accounts": [{"source": s, "account_id": s, "label": s,
                                  "identity": "default",
                                  "status": "done" if st == "success" else st,
                                  "rows": n or 0, "reports_done": 0, "error": e}
                                 for s, st, n, e in rows]}}

    # ---- claude ------------------------------------------------------------
    @app.get("/api/claude/detect")
    def get_claude_detect(request: Request) -> dict:
        check_token(request)
        from hub.setup_wizard import claude_config

        return claude_config.detect(config_path)

    @app.post("/api/claude/connect")
    def post_claude_connect(request: Request, body: dict) -> dict:
        check_token(request)
        from hub.setup_wizard import claude_config

        target = body.get("target", "")
        command, args = claude_config.mcp_command(config_path)
        try:
            if target == "cli":
                return {"written": "claude",
                        "output": claude_config.register_with_cli(command, args)}
            idx = int(target.split(":", 1)[1])
            path = claude_config.desktop_config_candidates()[idx]
            return {"written": str(claude_config.write_mcp_entry(path, command, args))}
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}

    # ---- version / schedule -------------------------------------------------
    @app.get("/api/version")
    def get_version(request: Request) -> dict:
        check_token(request)
        from hub.core import version

        latest, current = version.latest(), version.current()
        return {"current": current, "latest": latest["version"] if latest else None,
                "download_url": latest["url"] if latest else None,
                "update_available": bool(latest and version.is_newer(latest["version"], current))}

    @app.post("/api/schedule")
    def post_schedule(request: Request) -> dict:
        check_token(request)
        from hub.core import schedule

        try:
            return schedule.install_daily_sync(config_path, hour=6)
        except Exception as exc:  # noqa: BLE001
            return {"installed": False, "error": str(exc)}

    # ---- shutdown --------------------------------------------------------
    @app.post("/api/shutdown")
    def post_shutdown(request: Request) -> dict:
        check_token(request)
        state["shutdown"] = True

        def stop():
            time.sleep(0.5)
            import os
            os._exit(0)  # uvicorn has no clean stop from a handler; wizard is done

        threading.Thread(target=stop, daemon=True).start()
        return {"status": "bye"}

    return app


def run_setup(config_path: str | Path, port: int = 8770,
              open_browser: bool = True) -> None:
    """Serve the wizard on localhost and open it in the default browser."""
    import uvicorn

    app = create_setup_app(config_path)
    url = f"http://127.0.0.1:{port}"
    if open_browser:
        threading.Timer(1.0, webbrowser.open, args=[url]).start()
    print(f"Setup wizard: {url}  (Ctrl+C to stop)")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
