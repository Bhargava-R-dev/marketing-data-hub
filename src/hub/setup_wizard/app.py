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

from hub.core.config import load_config
from hub.dashboard import dashboard_router
from hub.setup_wizard.page import render_page


def create_setup_app(config_path: str | Path) -> FastAPI:
    config_path = Path(config_path).resolve()
    app = FastAPI(title="Marketing Data Hub Setup")
    app.include_router(dashboard_router(config_path))  # same-process "Open dashboard"
    run_token = secrets.token_hex(16)
    login_threads: dict[str, threading.Thread] = {}
    login_errors: dict[str, str] = {}
    state = {"shutdown": False}

    def cfg():
        return load_config(config_path)

    def check_token(request: Request) -> None:
        if request.headers.get("X-Setup-Token") != run_token:
            raise HTTPException(status_code=403, detail="bad setup token")

    # ---- page ----------------------------------------------------------
    @app.get("/", response_class=HTMLResponse)
    def page() -> str:
        return render_page(run_token, str(config_path))

    # ---- read state ----------------------------------------------------
    @app.get("/api/state")
    def get_state(request: Request) -> dict:
        check_token(request)
        from hub.connectors.google_auth import backfill_identity_labels, list_identities

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
                              "label": opts.get("labels", {}).get(str(i), str(i))}
                             for i in ids],
                "activated": source not in ("google_ads", "meta_ads") or bool(
                    opts.get("developer_token") or opts.get("access_token")),
            }
        coverage, busy = [], False
        try:
            conn = duckdb.connect(c.db_path, read_only=True)
            coverage = [{"source": s, "rows": n, "latest": str(latest)}
                        for s, n, latest in conn.execute(
                            """SELECT source, COUNT(*), MAX(date) FROM metrics
                               WHERE report='core' GROUP BY source""").fetchall()]
            conn.close()
        except Exception:  # noqa: BLE001 - db missing or locked by a sync
            busy = True
        return {"identities": identities,
                "logins_pending": [n for n, t in login_threads.items() if t.is_alive()],
                "login_errors": dict(login_errors),
                "connectors": connectors, "coverage": coverage, "db_busy": busy,
                "config_path": str(config_path)}

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
        client = Path(c.secrets_dir) / "google_client.json"
        if not client.exists():
            return {"error": f"Google sign-in file missing: put google_client.json "
                             f"in {c.secrets_dir}"}

        login_errors.pop(identity, None)  # clear any previous failure on retry

        def run_login():
            from hub.connectors.google_auth import login
            try:
                login(c.secrets_dir, identity=identity)
            except Exception as exc:  # noqa: BLE001 - surfaced via /api/state, not swallowed
                login_errors[identity] = str(exc)

        t = threading.Thread(target=run_login, daemon=True)
        t.start()
        login_threads[identity] = t
        return {"status": "started", "identity": identity,
                "note": "a Google sign-in tab opened - complete it there"}

    # ---- account discovery / add ----------------------------------------
    @app.get("/api/accounts")
    def get_accounts(request: Request, identity: str = "default",
                     source: str | None = None) -> list | dict:
        check_token(request)
        try:
            from hub.connectors.google_auth import get_credentials, token_path_for
            from hub.core.accounts import annotate_configured, discover_all

            c = cfg()
            if not token_path_for(c.secrets_dir, identity).exists():
                return {"error": f"identity {identity!r} is not connected yet"}
            creds = get_credentials(c.secrets_dir, identity=identity)
            return annotate_configured(discover_all(creds, source), c)
        except Exception as exc:  # noqa: BLE001 - show readable errors in the page
            return {"error": str(exc)}

    @app.post("/api/accounts/add")
    def post_accounts_add(request: Request, body: dict) -> dict:
        check_token(request)
        try:
            from hub.connectors.google_auth import get_credentials
            from hub.core.accounts import add_accounts, discover_all

            source = body["source"]
            ids = [str(i) for i in body.get("ids", [])]
            identity = body.get("identity") or "default"
            c = cfg()
            creds = get_credentials(c.secrets_dir, identity=identity)
            visible = {a["id"]: a for a in discover_all(creds, source)}
            unknown = [i for i in ids if i not in visible]
            if unknown:
                return {"error": f"not visible to this login: {unknown}"}
            added = add_accounts(config_path, source,
                                 [visible[i] for i in ids], identity=identity)
            return {"added": added}
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}

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
    @app.post("/api/sync")
    def post_sync(request: Request) -> dict:
        check_token(request)
        log_path = config_path.parent / "logs" / "setup_sync.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as log:
            log.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] setup wizard sync\n")
            log.flush()
            subprocess.Popen(
                [sys.executable, "-m", "hub.cli", "sync", "all",
                 "--config", str(config_path)],
                stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                creationflags=(subprocess.CREATE_NO_WINDOW
                               if sys.platform == "win32" else 0))
        return {"status": "started"}

    @app.get("/api/sync/status")
    def get_sync_status(request: Request) -> dict:
        check_token(request)
        c = cfg()
        try:
            conn = duckdb.connect(c.db_path, read_only=True)
            rows = conn.execute(
                """SELECT source, status, rows_written, error_message FROM sync_runs
                   QUALIFY ROW_NUMBER() OVER (PARTITION BY source
                   ORDER BY started_at DESC) = 1""").fetchall()
            conn.close()
            return {"runs": [{"source": s, "status": st, "rows": n, "error": e}
                             for s, st, n, e in rows],
                    "in_progress": any(r[1] == "running" for r in rows)}
        except Exception:  # noqa: BLE001 - write lock held = sync in flight
            return {"runs": [], "in_progress": True}

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
