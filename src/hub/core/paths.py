"""Where a hub lives on disk. One folder per user holds config, secrets, data,
logs and exports so the installer, pip, the scheduler and the MCP server all
agree without anyone passing --config."""
from __future__ import annotations

import os
import sys
from pathlib import Path

HOME_ENV = "HUB_HOME"
_DEFAULT_CONFIG = (
    "# created by 'hub setup' - accounts are added via the wizard\n"
    "db_path: data/hub.duckdb\nsecrets_dir: secrets\n"
    "exports_dir: exports\n\nconnectors: {}\n\nexports: []\n"
)


def python_exe() -> str:
    """The console interpreter, even when we were launched by pythonw.exe
    (a shortcut): child processes that talk over stdio (MCP, sync) need it."""
    exe = sys.executable
    if exe.lower().endswith("pythonw.exe"):
        return exe[:-len("pythonw.exe")] + "python.exe"
    return exe


def default_home() -> Path:
    override = os.environ.get(HOME_ENV)
    if override:
        return Path(override).resolve()
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return (Path(base) / "MarketingDataHub").resolve()
    return (Path.home() / ".marketing-data-hub").resolve()


def resolve_config_path(explicit: str | Path | None) -> Path:
    """--config wins; then a config.yaml in the current folder (keeps existing
    checkouts working untouched); else the per-user home."""
    if explicit:
        return Path(explicit).resolve()
    local = Path("config.yaml")
    if local.exists():
        return local.resolve()
    return default_home() / "config.yaml"


def ensure_home(home: Path) -> Path:
    """Create the folder layout and a minimal config if absent. Returns the
    config path. Never overwrites an existing config."""
    for sub in ("data", "secrets", "logs", "exports"):
        (home / sub).mkdir(parents=True, exist_ok=True)
    cfg = home / "config.yaml"
    if not cfg.exists():
        cfg.write_text(_DEFAULT_CONFIG, encoding="utf-8")
    return cfg
