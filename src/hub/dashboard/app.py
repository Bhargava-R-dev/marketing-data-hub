from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.responses import HTMLResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from hub.core.config import load_config
from hub.dashboard.data import build_dashboard
from hub.dashboard.page import render_dashboard_page


def dashboard_router(config_path: str | Path, prefix: str = "",
                     manage_url: str | None = None) -> APIRouter:
    """Routes for the dashboard — mountable standalone or inside another app
    (e.g. the setup wizard, so 'Open dashboard' needs no extra process).
    Read-only: no setup-token gate, same trust level as `hub status`.
    manage_url links to the (token-guarded) account management page when
    there is one in the same process."""
    config_path = Path(config_path).resolve()
    router = APIRouter()

    @router.get(prefix + "/dashboard", response_class=HTMLResponse)
    def dashboard_page() -> str:
        return render_dashboard_page(manage_url)

    @router.get(prefix + "/api/dashboard-data")
    def dashboard_data() -> dict:
        return build_dashboard(load_config(config_path))

    return router


def create_dashboard_app(config_path: str | Path) -> FastAPI:
    app = FastAPI(title="Marketing Data Hub Dashboard")
    app.add_middleware(TrustedHostMiddleware,
                       allowed_hosts=["127.0.0.1", "localhost"])
    app.include_router(dashboard_router(config_path))

    @app.get("/")
    def root() -> HTMLResponse:
        return HTMLResponse(render_dashboard_page())

    return app


def run_dashboard(config_path: str | Path, port: int = 8773,
                  open_browser: bool = True) -> None:
    from hub.core.local_server import serve_local

    app = create_dashboard_app(config_path)
    url = f"http://127.0.0.1:{port}"
    print(f"Dashboard: {url}  (Ctrl+C to stop)")
    serve_local(app, port, open_browser=open_browser)
