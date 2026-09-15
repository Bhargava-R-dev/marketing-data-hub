from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


class ConnectorSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schedule: str = "0 6 * * *"
    window_days: int = 30
    options: dict = Field(default_factory=dict)


class ExportConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    fields: list[str]
    sources: list[str] | None = None
    report: str = "core"
    date_preset: str = "last_30d"
    filename: str | None = None  # defaults to <name>.csv


class HubConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    db_path: str = "data/hub.duckdb"
    secrets_dir: str = "secrets"
    exports_dir: str = "exports"
    # the folder config.yaml lives in (set by load_config): logs, progress and
    # anything else "beside the config" derive from it, never from db_path
    home: str = ""
    connectors: dict[str, ConnectorSettings] = Field(default_factory=dict)
    exports: list[ExportConfig] = Field(default_factory=list)

    def model_post_init(self, __context) -> None:
        if not self.home:
            # built directly rather than via load_config (every test does this,
            # and it's a supported way to use HubConfig) - fall back to db_path's
            # own location instead of the process's cwd, which could be any
            # unrelated directory. This bit a test: with home defaulting to ".",
            # it silently read THIS REPO's real logs/sync_progress.json instead
            # of the isolated tmp_path the rest of the config pointed at.
            self.home = str(Path(self.db_path).resolve().parent.parent)


def load_config(path: str | Path = "config.yaml") -> HubConfig:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Config file not found: {path}. Copy config.yaml.example to config.yaml.")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cfg = HubConfig(**data)
    # Resolve relative storage paths against the config file's own directory so
    # the whole folder is portable: copy it to any machine / user / location and
    # it just works, regardless of the process's working directory (the MCP
    # server, scheduler, and CLI all launch from different cwds). Absolute paths
    # are left untouched.
    base = path.resolve().parent
    cfg.home = str(base)
    for attr in ("db_path", "secrets_dir", "exports_dir"):
        value = Path(getattr(cfg, attr))
        if not value.is_absolute():
            setattr(cfg, attr, str((base / value).resolve()))
    return cfg
