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
    connectors: dict[str, ConnectorSettings] = Field(default_factory=dict)
    exports: list[ExportConfig] = Field(default_factory=list)


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
    for attr in ("db_path", "secrets_dir", "exports_dir"):
        value = Path(getattr(cfg, attr))
        if not value.is_absolute():
            setattr(cfg, attr, str((base / value).resolve()))
    return cfg
