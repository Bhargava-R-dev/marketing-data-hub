from __future__ import annotations

from datetime import datetime
from pathlib import Path

import typer

from hub.core.config import HubConfig, load_config

app = typer.Typer(help="Marketing Data Hub — personal Windsor.ai replica")

CONFIG_OPT = typer.Option("config.yaml", "--config", help="Path to config.yaml")


def _load(config_path: str) -> HubConfig:
    if not Path(config_path).exists():
        typer.echo(f"Config not found: {config_path} (copy config.yaml.example)")
        raise typer.Exit(1)
    return load_config(config_path)


def _sources_to_sync(source: str, config: HubConfig) -> list[str]:
    if source == "all":
        return list(config.connectors)
    return [source]


@app.command()
def sync(source: str = typer.Argument("all"), config: str = CONFIG_OPT,
         window: int | None = typer.Option(None, help="Override window_days")):
    """Sync one connector (or 'all') over its rolling window."""
    from hub.connectors.catalog import build_connector
    from hub.core.storage import Storage
    from hub.core.sync import run_sync

    cfg = _load(config)
    storage = Storage(cfg.db_path)
    failures = 0
    for src in _sources_to_sync(source, cfg):
        try:
            connector = build_connector(src, cfg)
            days = window or cfg.connectors[src].window_days
            n = run_sync(storage, connector, window_days=days)
            typer.echo(f"[OK] {src}: {n} rows")
        except Exception as exc:  # noqa: BLE001
            typer.echo(f"[FAIL] {src}: {exc}")
            failures += 1
    try:
        _run_exports(cfg, storage)
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"[FAIL] exports: {exc}")
        failures += 1
    raise typer.Exit(1 if failures else 0)


@app.command()
def backfill(source: str, config: str = CONFIG_OPT,
             from_: str = typer.Option(..., "--from", help="YYYY-MM-DD"),
             to: str | None = typer.Option(None, "--to", help="YYYY-MM-DD")):
    """Backfill history in <=90-day chunks."""
    from hub.connectors.catalog import build_connector
    from hub.core.storage import Storage
    from hub.core.sync import backfill as run_backfill

    try:
        date_from = datetime.strptime(from_, "%Y-%m-%d").date()
        date_to = datetime.strptime(to, "%Y-%m-%d").date() if to else None
    except ValueError:
        typer.echo("[FAIL] dates must be YYYY-MM-DD, e.g. --from 2024-01-01")
        raise typer.Exit(1)
    cfg = _load(config)
    storage = Storage(cfg.db_path)
    connector = build_connector(source, cfg)
    n = run_backfill(storage, connector, date_from, date_to)
    typer.echo(f"[OK] {source}: {n} rows backfilled")


@app.command()
def status(config: str = CONFIG_OPT):
    """Show every connector's status, row counts, and last sync."""
    from hub.core.status import source_statuses
    from hub.core.storage import Storage

    cfg = _load(config)
    storage = Storage(cfg.db_path)
    for s in source_statuses(cfg, storage):
        run = s["last_sync"]
        last = f"{run['status']} at {run['started_at']}" if run else "never"
        typer.echo(f"{s['source']:<12} {s['status']:<9} rows={s['rows']:<8} "
                   f"latest={s['latest_date']} last_sync={last}")


@app.command()
def doctor(config: str = CONFIG_OPT):
    """Live-check auth + a 1-day probe for each configured connector."""
    from datetime import date, timedelta

    from hub.connectors.base import AuthError
    from hub.connectors.catalog import build_connector
    from hub.core.storage import Storage

    cfg = _load(config)
    Storage(cfg.db_path)  # verifies DB is creatable/writable
    typer.echo("[OK] database writable")
    if not cfg.connectors:
        typer.echo("No connectors configured. Add one to config.yaml.")
        raise typer.Exit(0)
    yesterday = date.today() - timedelta(days=1)
    failures = 0
    for src in cfg.connectors:
        try:
            connector = build_connector(src, cfg)
            connector.authenticate()
            rows = list(connector.extract(yesterday, yesterday))
            typer.echo(f"[OK] {src}: auth ok, probe returned {len(rows)} rows")
        except AuthError as exc:
            typer.echo(f"[FAIL] {src}: {exc}\n       hint: {exc.hint}")
            failures += 1
        except Exception as exc:  # noqa: BLE001
            typer.echo(f"[FAIL] {src}: {exc}")
            failures += 1
    raise typer.Exit(1 if failures else 0)


@app.command()
def export(name: str = typer.Argument("all"), config: str = CONFIG_OPT):
    """Run configured CSV exports."""
    from hub.core.storage import Storage

    cfg = _load(config)
    storage = Storage(cfg.db_path)
    _run_exports(cfg, storage, only=None if name == "all" else name)


def _run_exports(cfg: HubConfig, storage, only: str | None = None) -> None:
    from hub.destinations.csv_export import run_export

    for exp in cfg.exports:
        if only and exp.name != only:
            continue
        path = run_export(storage, exp, cfg.exports_dir)
        typer.echo(f"[OK] export {exp.name} -> {path}")


@app.command()
def serve(config: str = CONFIG_OPT, host: str = "127.0.0.1", port: int = 8000):
    """Run the query API + scheduler."""
    import uvicorn
    from dotenv import load_dotenv

    from hub.api.app import create_app
    from hub.core.storage import Storage
    from hub.scheduler.runner import build_scheduler

    load_dotenv()
    cfg = _load(config)
    storage = Storage(cfg.db_path)
    scheduler = build_scheduler(cfg, storage)
    scheduler.start()
    try:
        uvicorn.run(create_app(cfg, storage=storage), host=host, port=port)
    finally:
        scheduler.shutdown(wait=False)


@app.command()
def mcp(config: str = CONFIG_OPT):
    """Run the MCP server over stdio (register in Claude config)."""
    from hub.mcp.server import build_mcp

    cfg = _load(config)
    build_mcp(cfg, config_path=config).run()


if __name__ == "__main__":
    app()
