from __future__ import annotations

import threading
import webbrowser
from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.responses import HTMLResponse

from hub.core.config import load_config
from hub.dashboard.data import build_dashboard
from hub.dashboard.page import render_dashboard_page


def dashboard_router(config_path: str | Path, prefix: str = "") -> APIRouter:
    """Routes for the dashboard — mountable standalone or inside another app
    (e.g. the setup wizard, so 'Open dashboard' needs no extra process).
    Read-only: no setup-token gate, same trust level as `hub status`."""
    config_path = Path(config_path).resolve()
    router = APIRouter()

    @router.get(prefix + "/dashboard", response_class=HTMLResponse)
    def dashboard_page() -> str:
        return render_dashboard_page()

    @router.get(prefix + "/api/dashboard-data")
    def dashboard_data() -> dict:
        return build_dashboard(load_config(config_path))

    return router


def create_dashboard_app(config_path: str | Path) -> FastAPI:
    app = FastAPI(title="Marketing Data Hub Dashboard")
    app.include_router(dashboard_router(config_path))

    @app.get("/")
    def root() -> HTMLResponse:
        return HTMLResponse(render_dashboard_page())

    return app


def run_dashboard(config_path: str | Path, port: int = 8773,
                  open_browser: bool = True) -> None:
    import uvicorn

    app = create_dashboard_app(config_path)
    url = f"http://127.0.0.1:{port}"
    if open_browser:
        threading.Timer(1.0, webbrowser.open, args=[url]).start()
    print(f"Dashboard: {url}  (Ctrl+C to stop)")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
