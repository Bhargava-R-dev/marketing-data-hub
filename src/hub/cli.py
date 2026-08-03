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
    try:
        connector = build_connector(source, cfg)
    except KeyError as exc:
        typer.echo(f"[FAIL] {source}: {exc}")
        raise typer.Exit(1)
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
def dashboard(config: str = CONFIG_OPT,
             port: int = typer.Option(8773, help="Local port for the dashboard"),
             no_browser: bool = typer.Option(False, "--no-browser",
                                             help="Don't auto-open the browser")):
    """Open the read-only dashboard: what's synced, per brand, anytime.

    Works independently of 'hub setup' - check what data you have without
    going through setup again."""
    from hub.dashboard import run_dashboard

    _load(config)  # fail fast with a clear message if config.yaml is missing
    run_dashboard(config, port=port, open_browser=not no_browser)


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
def setup(config: str = CONFIG_OPT,
          port: int = typer.Option(8770, help="Local port for the wizard"),
          no_browser: bool = typer.Option(False, "--no-browser",
                                          help="Don't auto-open the browser")):
    """Open the browser setup wizard (the friendly, no-terminal path).

    Connect Google accounts, tick the properties/sites to sync, paste ad
    platform tokens, run the first sync, and copy the Claude MCP snippet -
    all from one local page. Creates config.yaml from the example if absent."""
    from pathlib import Path as _Path

    from hub.setup_wizard import run_setup

    cfg_path = _Path(config)
    if not cfg_path.exists():
        # a clean minimal config: the wizard fills in real accounts (the
        # .example file has placeholder ids that would break a first sync)
        cfg_path.write_text(
            "# created by 'hub setup' - accounts are added via the wizard\n"
            "db_path: data/hub.duckdb\nsecrets_dir: secrets\n"
            "exports_dir: exports\n\nconnectors: {}\n\nexports: []\n",
            encoding="utf-8")
        # loud and unmissable: running 'hub setup' from the wrong folder
        # silently starting a brand-new, empty hub there is a real footgun,
        # especially for a non-technical user who won't notice a relative path
        typer.echo("=" * 60)
        typer.echo(f"[NEW HUB] No existing config found - starting a fresh one at:")
        typer.echo(f"          {cfg_path.resolve()}")
        typer.echo("          If you meant to open your EXISTING hub instead, press")
        typer.echo("          Ctrl+C now, 'cd' into that folder, and run 'hub setup' "
                   "again")
        typer.echo("          (or pass --config <path to your existing config.yaml>).")
        typer.echo("=" * 60)
    run_setup(config, port=port, open_browser=not no_browser)


@app.command()
def login(name: str = typer.Argument(
              "default", help="Identity name for this Google login (e.g. personal)"),
          config: str = CONFIG_OPT):
    """Authorize an (additional) Google account.

    Each login is saved as its own identity: 'default' is the original
    google_token.json; any other name becomes google_token_<name>.json.
    Properties/sites are assigned to identities via 'hub accounts --identity
    <name> --add' (or options.identities in config.yaml)."""
    from hub.connectors.google_auth import list_identities
    from hub.connectors.google_auth import login as google_login

    cfg = _load(config)
    typer.echo(f"Opening browser - sign in with the Google account for identity {name!r}...")
    google_login(cfg.secrets_dir, identity=name)
    typer.echo(f"[OK] saved. Identities now available: {list_identities(cfg.secrets_dir)}")
    typer.echo(f"Next: hub accounts --identity {name} --add")


@app.command()
def accounts(source: str | None = typer.Argument(
                 None, help="ga4 | gsc (default: both)"),
             add: bool = typer.Option(False, "--add", help="Select and add accounts"),
             ids: list[str] = typer.Option(
                 None, "--id", help="Add these ids non-interactively (with --add)"),
             identity: str = typer.Option(
                 "default", "--identity",
                 help="Which Google login to browse (see 'hub login')"),
             config: str = CONFIG_OPT):
    """List every account a Google login can see; --add to select & save.

    Windsor-style onboarding: shows all GA4 properties / GSC sites available
    to the authorized token, marks configured ones, and writes selections to
    config.yaml (labels auto-filled from the account names). With multiple
    Google logins, pass --identity to browse each one; added accounts remember
    which identity owns them."""
    from hub.connectors.google_auth import get_credentials
    from hub.core.accounts import add_accounts, annotate_configured, discover_all

    cfg = _load(config)
    creds = get_credentials(cfg.secrets_dir, identity=identity)
    found = annotate_configured(discover_all(creds, source), cfg)
    if not found:
        typer.echo("No accounts visible to this Google login.")
        raise typer.Exit(0)

    by_num = {}
    for n, a in enumerate(sorted(found, key=lambda a: (a["source"], a["parent"], a["name"])), 1):
        by_num[n] = a
        mark = "*" if a["configured"] else " "
        parent = f" ({a['parent']})" if a["parent"] and a["parent"] != a["name"] else ""
        typer.echo(f"{n:>4} [{mark}] {a['source']:4} {a['name']}{parent}  ->  {a['id']}")
    typer.echo("\n  [*] = already in config.yaml")

    if not add:
        typer.echo("Run again with --add to select accounts to configure.")
        raise typer.Exit(0)

    if ids:
        chosen = [a for a in found if a["id"] in set(ids)]
        missing = set(ids) - {a["id"] for a in chosen}
        if missing:
            typer.echo(f"[FAIL] not visible to this login: {sorted(missing)}")
            raise typer.Exit(1)
    else:
        raw = typer.prompt("\nNumbers to add (comma-separated, e.g. 3,7,12)")
        try:
            chosen = [by_num[int(x)] for x in raw.replace(" ", "").split(",") if x]
        except (KeyError, ValueError):
            typer.echo("[FAIL] enter numbers from the list, comma-separated")
            raise typer.Exit(1)

    added_total = 0
    for src in ("ga4", "gsc"):
        sels = [a for a in chosen if a["source"] == src and not a["configured"]]
        if not sels:
            continue
        added = add_accounts(config, src, sels, identity=identity)
        added_total += len(added)
        for a in sels:
            typer.echo(f"[OK] added {src}: {a['name']} ({a['id']})"
                       + (f" [identity: {identity}]" if identity != "default" else ""))
    skipped = [a for a in chosen if a["configured"]]
    for a in skipped:
        typer.echo(f"[SKIP] already configured: {a['id']}")
    if added_total:
        typer.echo(f"\nSaved to {config}. Next: hub sync all  "
                   f"(and hub backfill <source> --from ... for history)")


@app.command()
def mcp(config: str = CONFIG_OPT):
    """Run the MCP server over stdio (register in Claude config)."""
    from hub.mcp.server import build_mcp

    cfg = _load(config)
    build_mcp(cfg, config_path=config).run()


if __name__ == "__main__":
    app()
