from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class ConnectorSettings(BaseModel):
    schedule: str = "0 6 * * *"
    window_days: int = 30
    options: dict = Field(default_factory=dict)


class ExportConfig(BaseModel):
    name: str
    fields: list[str]
    sources: list[str] | None = None
    date_preset: str = "last_30d"
    filename: str | None = None  # defaults to <name>.csv


class HubConfig(BaseModel):
    db_path: str = "data/hub.duckdb"
    secrets_dir: str = "secrets"
    exports_dir: str = "exports"
    connectors: dict[str, ConnectorSettings] = Field(default_factory=dict)
    exports: list[ExportConfig] = Field(default_factory=list)


def load_config(path: str | Path = "config.yaml") -> HubConfig:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return HubConfig(**data)
