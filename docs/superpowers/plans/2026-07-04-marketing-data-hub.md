# Marketing Data Hub Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a personal Windsor.ai replica: connectors pull marketing data (GA4, Search Console, YouTube live; Google Ads, Meta Ads dormant) into a unified DuckDB schema, exposed via a Windsor-style FastAPI query API, scheduled CSV exports, and an MCP server for Claude.

**Architecture:** Plugin connectors emit dicts keyed by unified field names → normalizer splits core columns from `extras` JSON → DuckDB `metrics` table with transactional rolling-window replace. One process serves FastAPI + APScheduler; the MCP server is a separate read-only process. Spec: `docs/superpowers/specs/2026-07-04-marketing-data-hub-design.md`.

**Tech Stack:** Python 3.11+, duckdb, fastapi, uvicorn, apscheduler, fastmcp, pydantic v2, typer, pyyaml, python-dotenv, google-analytics-data, google-api-python-client, google-auth-oauthlib. Optional extras: google-ads, facebook-business.

**Conventions for all tasks:**
- Run tests with `python -m pytest <path> -v` from the repo root.
- All source files live under `src/hub/`; the package is installed editable so `import hub` works.
- Commit after every green test run. Never commit with failing tests.

## File structure

```
pyproject.toml
config.yaml.example        # copy to config.yaml (gitignored)
.env.example               # HUB_API_KEY (copy to .env, gitignored)
src/hub/
  core/models.py           # UnifiedRow, SyncRun, core column lists
  core/config.py           # HubConfig + load_config()
  core/storage.py          # DuckDB layer: schema, replace_rows, query, sync log
  core/normalizer.py       # raw dicts -> UnifiedRow
  core/sync.py             # run_sync (retries, rolling window), backfill
  core/presets.py          # date_preset -> (date_from, date_to)
  core/status.py           # source_statuses() shared by API/MCP/CLI
  connectors/base.py       # FieldSpec, FieldRegistry, BaseConnector, AuthError
  connectors/google_auth.py
  connectors/ga4.py  connectors/gsc.py  connectors/youtube.py
  connectors/google_ads.py  connectors/meta_ads.py     # dormant
  connectors/catalog.py    # ALL_CONNECTORS + build_connector()
  api/app.py               # create_app()
  destinations/csv_export.py
  scheduler/runner.py
  mcp/server.py
  cli.py                   # typer: sync backfill status doctor serve export mcp
tests/                     # mirrors src, fixtures inline
```

---

### Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `.env.example`, `config.yaml.example`
- Create: `src/hub/__init__.py` (+ empty `__init__.py` in `core/`, `connectors/`, `api/`, `destinations/`, `scheduler/`, `mcp/`)
- Create: `tests/__init__.py`, `tests/test_scaffold.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "marketing-data-hub"
version = "0.1.0"
description = "Personal Windsor.ai-style marketing data pipeline"
requires-python = ">=3.11"
dependencies = [
    "duckdb>=1.0",
    "fastapi>=0.110",
    "uvicorn>=0.29",
    "apscheduler>=3.10,<4",
    "pydantic>=2.6",
    "pyyaml>=6.0",
    "typer>=0.12",
    "fastmcp>=2.0",
    "python-dotenv>=1.0",
    "google-analytics-data>=0.18",
    "google-api-python-client>=2.120",
    "google-auth-oauthlib>=1.2",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "httpx>=0.27"]
googleads = ["google-ads>=24.0"]
meta = ["facebook-business>=19.0"]

[project.scripts]
hub = "hub.cli:app"

[tool.hatch.build.targets.wheel]
packages = ["src/hub"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Create .gitignore**

```
__pycache__/
*.egg-info/
.venv/
.env
config.yaml
secrets/
data/
exports/
.pytest_cache/
```

- [ ] **Step 3: Create .env.example**

```
HUB_API_KEY=change-me-to-a-long-random-string
```

- [ ] **Step 4: Create config.yaml.example**

```yaml
db_path: data/hub.duckdb
secrets_dir: secrets
exports_dir: exports

connectors:
  ga4:
    schedule: "0 6 * * *"
    window_days: 30
    options:
      property_id: "123456789"
  gsc:
    schedule: "0 6 * * *"
    options:
      site_url: "sc-domain:example.com"
  youtube:
    schedule: "0 6 * * *"
    options: {}
  # google_ads:            # activate when you have a developer token
  #   options:
  #     customer_id: "1234567890"
  #     login_customer_id: "1234567890"
  #     developer_token: "..."
  # meta_ads:              # activate when you have a Meta app + token
  #   options:
  #     ad_account_id: "act_123"
  #     access_token: "..."

exports:
  - name: daily_overview
    fields: [date, source, impressions, clicks, spend, sessions, conversions]
    date_preset: last_30d
```

- [ ] **Step 5: Create package skeleton**

Create empty `__init__.py` files: `src/hub/__init__.py`, `src/hub/core/__init__.py`, `src/hub/connectors/__init__.py`, `src/hub/api/__init__.py`, `src/hub/destinations/__init__.py`, `src/hub/scheduler/__init__.py`, `src/hub/mcp/__init__.py`, `tests/__init__.py`.

- [ ] **Step 6: Write the sanity test**

`tests/test_scaffold.py`:
```python
def test_package_imports():
    import hub
    assert hub is not None
```

- [ ] **Step 7: Install and run**

Run: `python -m pip install -e ".[dev]"`
Run: `python -m pytest tests/test_scaffold.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml .gitignore .env.example config.yaml.example src tests
git commit -m "feat: project scaffold for marketing data hub"
```

---

### Task 2: Unified data model + normalizer

**Files:**
- Create: `src/hub/core/models.py`, `src/hub/core/normalizer.py`
- Test: `tests/test_normalizer.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_normalizer.py`:
```python
from datetime import date

from hub.core.models import CORE_DIMENSIONS, CORE_METRICS, UnifiedRow
from hub.core.normalizer import normalize


def test_core_column_lists():
    assert "date" in CORE_DIMENSIONS and "campaign" in CORE_DIMENSIONS
    assert "spend" in CORE_METRICS and "conversions" in CORE_METRICS


def test_normalize_splits_core_and_extras():
    raw = [{
        "date": "2026-07-01", "account_id": "prop-1", "account_name": "My Site",
        "campaign": "summer", "clicks": "42", "spend": 3.5,
        "position": 12.3, "ctr": 0.04,
    }]
    rows = normalize("gsc", raw)
    assert len(rows) == 1
    r = rows[0]
    assert isinstance(r, UnifiedRow)
    assert r.source == "gsc"
    assert r.date == date(2026, 7, 1)
    assert r.clicks == 42           # coerced from string
    assert r.spend == 3.5
    assert r.extras == {"position": 12.3, "ctr": 0.04}
    assert r.impressions is None    # unset metric stays None


def test_normalize_requires_date_and_account():
    import pytest
    with pytest.raises(Exception):
        normalize("ga4", [{"clicks": 1}])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_normalizer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'hub.core.models'`

- [ ] **Step 3: Implement models.py**

`src/hub/core/models.py`:
```python
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

CORE_DIMENSIONS = ["date", "source", "account_id", "account_name", "campaign_id", "campaign"]
CORE_METRICS = ["impressions", "clicks", "spend", "conversions", "conversion_value", "sessions", "users"]
CORE_FIELDS = set(CORE_DIMENSIONS) | set(CORE_METRICS)


class UnifiedRow(BaseModel):
    date: date
    source: str
    account_id: str
    account_name: str = ""
    campaign_id: str | None = None
    campaign: str | None = None
    impressions: int | None = None
    clicks: int | None = None
    spend: float | None = None
    conversions: float | None = None
    conversion_value: float | None = None
    sessions: int | None = None
    users: int | None = None
    extras: dict = Field(default_factory=dict)


class SyncRun(BaseModel):
    id: int | None = None
    source: str
    started_at: datetime
    finished_at: datetime | None = None
    date_from: date
    date_to: date
    rows_written: int = 0
    status: str = "running"  # running | success | error
    error_message: str | None = None
```

- [ ] **Step 4: Implement normalizer.py**

`src/hub/core/normalizer.py`:
```python
from __future__ import annotations

from typing import Iterable

from hub.core.models import CORE_FIELDS, UnifiedRow


def normalize(source: str, raw_rows: Iterable[dict]) -> list[UnifiedRow]:
    """Split connector output into core columns + extras and validate."""
    out: list[UnifiedRow] = []
    for raw in raw_rows:
        core = {k: v for k, v in raw.items() if k in CORE_FIELDS and k != "source"}
        extras = {k: v for k, v in raw.items() if k not in CORE_FIELDS}
        out.append(UnifiedRow(source=source, extras=extras, **core))
    return out
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_normalizer.py -v`
Expected: 3 PASS

- [ ] **Step 6: Commit**

```bash
git add src/hub/core/models.py src/hub/core/normalizer.py tests/test_normalizer.py
git commit -m "feat: unified data model and normalizer"
```

---

### Task 3: Config loading

**Files:**
- Create: `src/hub/core/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_config.py`:
```python
from pathlib import Path

from hub.core.config import HubConfig, load_config


def test_load_config(tmp_path: Path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        """
db_path: data/hub.duckdb
connectors:
  ga4:
    window_days: 14
    options:
      property_id: "123"
exports:
  - name: overview
    fields: [date, clicks]
    date_preset: last_7d
""",
        encoding="utf-8",
    )
    cfg = load_config(cfg_file)
    assert isinstance(cfg, HubConfig)
    assert cfg.db_path == "data/hub.duckdb"
    assert cfg.connectors["ga4"].window_days == 14
    assert cfg.connectors["ga4"].schedule == "0 6 * * *"  # default
    assert cfg.connectors["ga4"].options["property_id"] == "123"
    assert cfg.exports[0].name == "overview"
    assert cfg.exports[0].date_preset == "last_7d"


def test_defaults_when_sections_missing(tmp_path: Path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("db_path: x.duckdb\n", encoding="utf-8")
    cfg = load_config(cfg_file)
    assert cfg.connectors == {}
    assert cfg.exports == []
    assert cfg.secrets_dir == "secrets"
    assert cfg.exports_dir == "exports"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement config.py**

`src/hub/core/config.py`:
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_config.py -v`
Expected: 2 PASS

- [ ] **Step 5: Commit**

```bash
git add src/hub/core/config.py tests/test_config.py
git commit -m "feat: yaml config loading"
```

---

### Task 4: DuckDB storage layer

**Files:**
- Create: `src/hub/core/storage.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_storage.py`:
```python
from datetime import date

import pytest

from hub.core.models import UnifiedRow
from hub.core.storage import Storage


@pytest.fixture()
def store(tmp_path):
    return Storage(str(tmp_path / "test.duckdb"))


def rows_for(source, day, clicks, extras=None):
    return [UnifiedRow(date=day, source=source, account_id="a1", account_name="Acct",
                       clicks=clicks, impressions=clicks * 10, extras=extras or {})]


def test_replace_rows_is_idempotent(store):
    d = date(2026, 7, 1)
    assert store.replace_rows("ga4", d, d, rows_for("ga4", d, 5)) == 1
    assert store.replace_rows("ga4", d, d, rows_for("ga4", d, 7)) == 1  # replaces
    out = store.query(["date", "clicks"], d, d)
    assert out == [{"date": d, "clicks": 7}]


def test_replace_rows_scoped_to_source(store):
    d = date(2026, 7, 1)
    store.replace_rows("ga4", d, d, rows_for("ga4", d, 5))
    store.replace_rows("gsc", d, d, rows_for("gsc", d, 3))
    store.replace_rows("ga4", d, d, rows_for("ga4", d, 9))
    out = store.query(["source", "clicks"], d, d)
    assert sorted(out, key=lambda r: r["source"]) == [
        {"source": "ga4", "clicks": 9}, {"source": "gsc", "clicks": 3}]


def test_query_aggregates_metrics_over_dims(store):
    d1, d2 = date(2026, 7, 1), date(2026, 7, 2)
    store.replace_rows("ga4", d1, d2, rows_for("ga4", d1, 5) + rows_for("ga4", d2, 2))
    store.replace_rows("gsc", d1, d2, rows_for("gsc", d1, 3))
    out = store.query(["date", "clicks"], d1, d2)
    assert out == [{"date": d1, "clicks": 8}, {"date": d2, "clicks": 2}]


def test_query_extras_and_filters(store):
    d = date(2026, 7, 1)
    store.replace_rows("gsc", d, d, rows_for("gsc", d, 3, extras={"position": 12.5}))
    out = store.query(["date", "position", "clicks"], d, d, sources=["gsc"])
    assert out == [{"date": d, "position": "12.5", "clicks": 3}]  # extras come back as strings
    out = store.query(["date", "clicks"], d, d, filters={"account_id": "nope"})
    assert out == []


def test_query_rejects_bad_field_names(store):
    with pytest.raises(ValueError):
        store.query(["date; DROP TABLE metrics"], date(2026, 7, 1), date(2026, 7, 1))


def test_sync_run_lifecycle(store):
    run_id = store.start_sync("ga4", date(2026, 6, 1), date(2026, 7, 1))
    store.finish_sync(run_id, rows=10, status="success")
    runs = store.last_runs()
    assert runs["ga4"]["status"] == "success"
    assert runs["ga4"]["rows_written"] == 10


def test_status_counts(store):
    d = date(2026, 7, 1)
    store.replace_rows("ga4", d, d, rows_for("ga4", d, 5))
    counts = store.row_counts()
    assert counts["ga4"]["rows"] == 1
    assert counts["ga4"]["latest_date"] == d
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_storage.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement storage.py**

`src/hub/core/storage.py`:
```python
from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path

import duckdb

from hub.core.models import CORE_DIMENSIONS, CORE_METRICS, UnifiedRow

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS metrics (
        date DATE, source VARCHAR, account_id VARCHAR, account_name VARCHAR,
        campaign_id VARCHAR, campaign VARCHAR,
        impressions BIGINT, clicks BIGINT, spend DOUBLE, conversions DOUBLE,
        conversion_value DOUBLE, sessions BIGINT, users BIGINT, extras JSON)""",
    "CREATE SEQUENCE IF NOT EXISTS sync_runs_seq",
    """CREATE TABLE IF NOT EXISTS sync_runs (
        id BIGINT DEFAULT nextval('sync_runs_seq'), source VARCHAR,
        started_at TIMESTAMP, finished_at TIMESTAMP, date_from DATE, date_to DATE,
        rows_written BIGINT, status VARCHAR, error_message VARCHAR)""",
]


class Storage:
    def __init__(self, db_path: str, read_only: bool = False):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = duckdb.connect(db_path, read_only=read_only)
        if not read_only:
            for stmt in _SCHEMA:
                self.conn.execute(stmt)

    # ---- writes -------------------------------------------------------
    def replace_rows(self, source: str, date_from: date, date_to: date,
                     rows: list[UnifiedRow]) -> int:
        self.conn.execute("BEGIN TRANSACTION")
        try:
            self.conn.execute(
                "DELETE FROM metrics WHERE source = ? AND date BETWEEN ? AND ?",
                [source, date_from, date_to])
            for r in rows:
                self.conn.execute(
                    "INSERT INTO metrics VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [r.date, r.source, r.account_id, r.account_name, r.campaign_id,
                     r.campaign, r.impressions, r.clicks, r.spend, r.conversions,
                     r.conversion_value, r.sessions, r.users, json.dumps(r.extras)])
            self.conn.execute("COMMIT")
        except Exception:
            self.conn.execute("ROLLBACK")
            raise
        return len(rows)

    # ---- queries ------------------------------------------------------
    def query(self, fields: list[str], date_from: date, date_to: date,
              sources: list[str] | None = None,
              filters: dict[str, str] | None = None) -> list[dict]:
        for f in fields:
            if not _IDENT.match(f):
                raise ValueError(f"invalid field name: {f!r}")
        dims = [f for f in fields if f in CORE_DIMENSIONS]
        mets = [f for f in fields if f in CORE_METRICS]
        extra = [f for f in fields if f not in CORE_DIMENSIONS and f not in CORE_METRICS]

        sel = [f'"{d}"' for d in dims]
        sel += [f"json_extract_string(extras, '$.{e}') AS \"{e}\"" for e in extra]
        sel += [f'SUM("{m}") AS "{m}"' for m in mets]

        where = ["date BETWEEN ? AND ?"]
        params: list = [date_from, date_to]
        if sources:
            where.append(f"source IN ({','.join(['?'] * len(sources))})")
            params.extend(sources)
        for key, val in (filters or {}).items():
            if key not in CORE_DIMENSIONS:
                raise ValueError(f"invalid filter: {key!r}")
            where.append(f'"{key}" = ?')
            params.append(val)

        group_cols = dims + extra
        sql = f"SELECT {', '.join(sel)} FROM metrics WHERE {' AND '.join(where)}"
        if group_cols and mets:
            sql += f" GROUP BY {', '.join(str(i + 1) for i in range(len(group_cols)))}"
        if group_cols:
            sql += f" ORDER BY {', '.join(str(i + 1) for i in range(len(group_cols)))}"
        cur = self.conn.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def row_counts(self) -> dict[str, dict]:
        cur = self.conn.execute(
            "SELECT source, COUNT(*), MAX(date) FROM metrics GROUP BY source")
        return {s: {"rows": n, "latest_date": latest} for s, n, latest in cur.fetchall()}

    # ---- sync log -----------------------------------------------------
    def start_sync(self, source: str, date_from: date, date_to: date) -> int:
        cur = self.conn.execute(
            """INSERT INTO sync_runs (source, started_at, date_from, date_to,
               rows_written, status) VALUES (?, ?, ?, ?, 0, 'running') RETURNING id""",
            [source, datetime.now(), date_from, date_to])
        return cur.fetchone()[0]

    def finish_sync(self, run_id: int, rows: int, status: str,
                    error: str | None = None) -> None:
        self.conn.execute(
            """UPDATE sync_runs SET finished_at = ?, rows_written = ?,
               status = ?, error_message = ? WHERE id = ?""",
            [datetime.now(), rows, status, error, run_id])

    def last_runs(self) -> dict[str, dict]:
        cur = self.conn.execute(
            """SELECT source, started_at, finished_at, rows_written, status, error_message
               FROM sync_runs QUALIFY ROW_NUMBER() OVER
               (PARTITION BY source ORDER BY started_at DESC) = 1""")
        out = {}
        for s, started, finished, rows, status, err in cur.fetchall():
            out[s] = {"started_at": started, "finished_at": finished,
                      "rows_written": rows, "status": status, "error_message": err}
        return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_storage.py -v`
Expected: 7 PASS

- [ ] **Step 5: Commit**

```bash
git add src/hub/core/storage.py tests/test_storage.py
git commit -m "feat: duckdb storage with transactional replace, aggregation query, sync log"
```

---

### Task 5: Connector framework (FieldSpec, FieldRegistry, BaseConnector)

**Files:**
- Create: `src/hub/connectors/base.py`
- Test: `tests/test_base_connector.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_base_connector.py`:
```python
from hub.connectors.base import BaseConnector, FieldRegistry, FieldSpec


def test_registry_names_and_dict():
    reg = FieldRegistry([
        FieldSpec("date", "date", dimension=True),
        FieldSpec("clicks", "clicks"),
        FieldSpec("position", "position", description="avg SERP position"),
    ])
    assert reg.names() == ["date", "clicks", "position"]
    d = reg.to_dict()
    assert d[0] == {"name": "date", "native": "date", "dimension": True, "description": ""}
    assert d[2]["description"] == "avg SERP position"


def test_base_connector_is_abstract():
    import pytest
    with pytest.raises(TypeError):
        BaseConnector(settings=None, secrets_dir=".")  # type: ignore[abstract]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_base_connector.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement base.py**

`src/hub/connectors/base.py`:
```python
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import ClassVar, Iterable

from hub.core.config import ConnectorSettings


class AuthError(Exception):
    """Authentication problem with an actionable hint."""

    def __init__(self, message: str, hint: str = ""):
        super().__init__(message)
        self.hint = hint


@dataclass(frozen=True)
class FieldSpec:
    name: str            # unified name (core column or extras key)
    native: str          # native API field name
    dimension: bool = False
    description: str = ""


@dataclass
class FieldRegistry:
    specs: list[FieldSpec] = field(default_factory=list)

    def names(self) -> list[str]:
        return [s.name for s in self.specs]

    def native_to_unified(self) -> dict[str, str]:
        return {s.native: s.name for s in self.specs}

    def to_dict(self) -> list[dict]:
        return [{"name": s.name, "native": s.native, "dimension": s.dimension,
                 "description": s.description} for s in self.specs]


class BaseConnector(ABC):
    id: ClassVar[str]
    fields: ClassVar[FieldRegistry]

    def __init__(self, settings: ConnectorSettings, secrets_dir: str | Path):
        self.settings = settings
        self.secrets_dir = Path(secrets_dir)

    @abstractmethod
    def authenticate(self) -> None:
        """Load/refresh credentials. Raises AuthError with a fix hint."""

    @abstractmethod
    def extract(self, date_from: date, date_to: date) -> Iterable[dict]:
        """Yield dicts keyed by unified field names (registry names) plus
        account_id/account_name. The normalizer handles the rest."""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_base_connector.py -v`
Expected: 2 PASS

- [ ] **Step 5: Commit**

```bash
git add src/hub/connectors/base.py tests/test_base_connector.py
git commit -m "feat: connector framework (FieldSpec, FieldRegistry, BaseConnector)"
```

---

### Task 6: Date presets

**Files:**
- Create: `src/hub/core/presets.py`
- Test: `tests/test_presets.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_presets.py`:
```python
from datetime import date

import pytest

from hub.core.presets import resolve_dates

TODAY = date(2026, 7, 4)


def test_last_7d():
    assert resolve_dates("last_7d", today=TODAY) == (date(2026, 6, 27), TODAY)


def test_this_month_and_last_month():
    assert resolve_dates("this_month", today=TODAY) == (date(2026, 7, 1), TODAY)
    assert resolve_dates("last_month", today=TODAY) == (date(2026, 6, 1), date(2026, 6, 30))


def test_ytd():
    assert resolve_dates("ytd", today=TODAY) == (date(2026, 1, 1), TODAY)


def test_explicit_range_wins():
    assert resolve_dates(None, date_from=date(2026, 1, 5), date_to=date(2026, 1, 9)) == (
        date(2026, 1, 5), date(2026, 1, 9))


def test_unknown_preset_raises():
    with pytest.raises(ValueError):
        resolve_dates("last_fortnight", today=TODAY)


def test_no_args_defaults_to_last_30d():
    df, dt = resolve_dates(None, today=TODAY)
    assert (dt - df).days == 30 and dt == TODAY
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_presets.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement presets.py**

`src/hub/core/presets.py`:
```python
from __future__ import annotations

from datetime import date, timedelta

_RELATIVE = {"last_7d": 7, "last_30d": 30, "last_90d": 90}


def resolve_dates(preset: str | None = None, date_from: date | None = None,
                  date_to: date | None = None, today: date | None = None) -> tuple[date, date]:
    today = today or date.today()
    if date_from and date_to:
        return date_from, date_to
    if preset is None:
        return today - timedelta(days=30), today
    if preset in _RELATIVE:
        return today - timedelta(days=_RELATIVE[preset]), today
    if preset == "this_month":
        return today.replace(day=1), today
    if preset == "last_month":
        first_this = today.replace(day=1)
        last_prev = first_this - timedelta(days=1)
        return last_prev.replace(day=1), last_prev
    if preset == "ytd":
        return today.replace(month=1, day=1), today
    raise ValueError(f"unknown date_preset: {preset!r}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_presets.py -v`
Expected: 6 PASS

- [ ] **Step 5: Commit**

```bash
git add src/hub/core/presets.py tests/test_presets.py
git commit -m "feat: date preset resolution"
```

---

### Task 7: Google OAuth helper

**Files:**
- Create: `src/hub/connectors/google_auth.py`
- Test: `tests/test_google_auth.py`

Note: the interactive browser flow cannot run in tests; we test the error path and
the token-file path. Live verification happens via `hub doctor` (Task 15).

- [ ] **Step 1: Write the failing tests**

`tests/test_google_auth.py`:
```python
import json

import pytest

from hub.connectors.base import AuthError
from hub.connectors.google_auth import GOOGLE_SCOPES, get_credentials


def test_missing_client_file_raises_actionable_error(tmp_path):
    with pytest.raises(AuthError) as exc:
        get_credentials(tmp_path)
    assert "google_client.json" in exc.value.hint


def test_existing_valid_token_is_loaded(tmp_path):
    token = {
        "token": "abc", "refresh_token": "def",
        "client_id": "x", "client_secret": "y",
        "token_uri": "https://oauth2.googleapis.com/token",
        "scopes": GOOGLE_SCOPES,
        "expiry": "2099-01-01T00:00:00Z",
    }
    (tmp_path / "google_token.json").write_text(json.dumps(token), encoding="utf-8")
    creds = get_credentials(tmp_path)
    assert creds.token == "abc"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_google_auth.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement google_auth.py**

`src/hub/connectors/google_auth.py`:
```python
from __future__ import annotations

from pathlib import Path

from hub.connectors.base import AuthError

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/analytics.readonly",
    "https://www.googleapis.com/auth/webmasters.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/adwords",
]


def get_credentials(secrets_dir: str | Path, scopes: list[str] | None = None):
    """Return google.oauth2 Credentials. First run opens a browser consent flow."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    secrets_dir = Path(secrets_dir)
    scopes = scopes or GOOGLE_SCOPES
    token_path = secrets_dir / "google_token.json"
    client_path = secrets_dir / "google_client.json"

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), scopes)
        if creds.valid:
            return creds
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token_path.write_text(creds.to_json(), encoding="utf-8")
            return creds

    if not client_path.exists():
        raise AuthError(
            "No Google credentials found.",
            hint=("Create an OAuth client (Desktop app) in Google Cloud Console under "
                  "APIs & Services > Credentials, download the JSON, and save it as "
                  f"{client_path}. Then run: hub doctor"))

    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(str(client_path), scopes)
    creds = flow.run_local_server(port=0)
    secrets_dir.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json(), encoding="utf-8")
    return creds
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_google_auth.py -v`
Expected: 2 PASS

- [ ] **Step 5: Commit**

```bash
git add src/hub/connectors/google_auth.py tests/test_google_auth.py
git commit -m "feat: shared google oauth helper with token cache"
```

---

### Task 8: GA4 connector

**Files:**
- Create: `src/hub/connectors/ga4.py`
- Test: `tests/test_ga4.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_ga4.py`:
```python
from hub.connectors.ga4 import GA4_FIELDS, GA4Connector, parse_ga4_report

FIXTURE = {
    "dimensionHeaders": [{"name": "date"}, {"name": "sessionCampaignName"}],
    "metricHeaders": [{"name": "sessions"}, {"name": "totalUsers"},
                      {"name": "keyEvents"}, {"name": "purchaseRevenue"}],
    "rows": [
        {"dimensionValues": [{"value": "20260701"}, {"value": "summer_sale"}],
         "metricValues": [{"value": "120"}, {"value": "95"}, {"value": "4"}, {"value": "199.5"}]},
        {"dimensionValues": [{"value": "20260702"}, {"value": "(direct)"}],
         "metricValues": [{"value": "80"}, {"value": "70"}, {"value": "1"}, {"value": "0"}]},
    ],
}


def test_parse_ga4_report():
    rows = parse_ga4_report(FIXTURE, property_id="123")
    assert len(rows) == 2
    assert rows[0] == {
        "account_id": "123", "account_name": "GA4 123",
        "date": "2026-07-01", "campaign": "summer_sale",
        "sessions": "120", "users": "95", "conversions": "4",
        "conversion_value": "199.5",
    }


def test_parse_empty_report():
    assert parse_ga4_report({"rows": []}, property_id="123") == []


def test_connector_metadata():
    assert GA4Connector.id == "ga4"
    assert set(GA4_FIELDS.names()) == {
        "date", "campaign", "sessions", "users", "conversions", "conversion_value"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_ga4.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement ga4.py**

`src/hub/connectors/ga4.py`:
```python
from __future__ import annotations

from datetime import date
from typing import Iterable

from hub.connectors.base import BaseConnector, FieldRegistry, FieldSpec
from hub.connectors.google_auth import get_credentials

GA4_FIELDS = FieldRegistry([
    FieldSpec("date", "date", dimension=True),
    FieldSpec("campaign", "sessionCampaignName", dimension=True),
    FieldSpec("sessions", "sessions"),
    FieldSpec("users", "totalUsers"),
    FieldSpec("conversions", "keyEvents"),
    FieldSpec("conversion_value", "purchaseRevenue"),
])

_N2U = GA4_FIELDS.native_to_unified()


def parse_ga4_report(report: dict, property_id: str) -> list[dict]:
    dims = [h["name"] for h in report.get("dimensionHeaders", [])]
    mets = [h["name"] for h in report.get("metricHeaders", [])]
    out = []
    for row in report.get("rows", []):
        raw: dict = {"account_id": property_id, "account_name": f"GA4 {property_id}"}
        for name, v in zip(dims, row["dimensionValues"]):
            raw[_N2U[name]] = v["value"]
        for name, v in zip(mets, row["metricValues"]):
            raw[_N2U[name]] = v["value"]
        d = raw["date"]  # GA4 returns YYYYMMDD
        raw["date"] = f"{d[:4]}-{d[4:6]}-{d[6:]}"
        out.append(raw)
    return out


class GA4Connector(BaseConnector):
    id = "ga4"
    fields = GA4_FIELDS

    def authenticate(self) -> None:
        self._creds = get_credentials(self.secrets_dir)

    def extract(self, date_from: date, date_to: date) -> Iterable[dict]:
        from google.analytics.data_v1beta import BetaAnalyticsDataClient
        from google.analytics.data_v1beta.types import (
            DateRange, Dimension, Metric, RunReportRequest, RunReportResponse)

        property_id = self.settings.options["property_id"]
        client = BetaAnalyticsDataClient(credentials=self._creds)
        request = RunReportRequest(
            property=f"properties/{property_id}",
            dimensions=[Dimension(name=s.native) for s in GA4_FIELDS.specs if s.dimension],
            metrics=[Metric(name=s.native) for s in GA4_FIELDS.specs if not s.dimension],
            date_ranges=[DateRange(start_date=date_from.isoformat(),
                                   end_date=date_to.isoformat())],
            limit=250000,
        )
        response = client.run_report(request)
        report = RunReportResponse.to_dict(response, preserving_proto_field_name=False)
        return parse_ga4_report(report, property_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_ga4.py -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add src/hub/connectors/ga4.py tests/test_ga4.py
git commit -m "feat: GA4 connector"
```

---

### Task 9: Search Console connector

**Files:**
- Create: `src/hub/connectors/gsc.py`
- Test: `tests/test_gsc.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_gsc.py`:
```python
from hub.connectors.gsc import GSC_FIELDS, SearchConsoleConnector, parse_gsc_response

FIXTURE = {
    "rows": [
        {"keys": ["2026-07-01"], "clicks": 31, "impressions": 820,
         "ctr": 0.0378, "position": 14.2},
        {"keys": ["2026-07-02"], "clicks": 27, "impressions": 790,
         "ctr": 0.0342, "position": 15.1},
    ]
}


def test_parse_gsc_response():
    rows = parse_gsc_response(FIXTURE, site_url="sc-domain:example.com")
    assert rows[0] == {
        "account_id": "sc-domain:example.com", "account_name": "sc-domain:example.com",
        "date": "2026-07-01", "clicks": 31, "impressions": 820,
        "ctr": 0.0378, "position": 14.2,
    }


def test_parse_empty_response():
    assert parse_gsc_response({}, site_url="x") == []


def test_connector_metadata():
    assert SearchConsoleConnector.id == "gsc"
    assert set(GSC_FIELDS.names()) == {"date", "clicks", "impressions", "ctr", "position"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_gsc.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement gsc.py**

`src/hub/connectors/gsc.py`:
```python
from __future__ import annotations

from datetime import date
from typing import Iterable

from hub.connectors.base import BaseConnector, FieldRegistry, FieldSpec
from hub.connectors.google_auth import get_credentials

GSC_FIELDS = FieldRegistry([
    FieldSpec("date", "date", dimension=True),
    FieldSpec("clicks", "clicks"),
    FieldSpec("impressions", "impressions"),
    FieldSpec("ctr", "ctr", description="click-through rate (extras)"),
    FieldSpec("position", "position", description="avg SERP position (extras)"),
])


def parse_gsc_response(resp: dict, site_url: str) -> list[dict]:
    out = []
    for row in resp.get("rows", []):
        out.append({
            "account_id": site_url, "account_name": site_url,
            "date": row["keys"][0],
            "clicks": row.get("clicks"), "impressions": row.get("impressions"),
            "ctr": row.get("ctr"), "position": row.get("position"),
        })
    return out


class SearchConsoleConnector(BaseConnector):
    id = "gsc"
    fields = GSC_FIELDS

    def authenticate(self) -> None:
        self._creds = get_credentials(self.secrets_dir)

    def extract(self, date_from: date, date_to: date) -> Iterable[dict]:
        from googleapiclient.discovery import build

        site_url = self.settings.options["site_url"]
        service = build("searchconsole", "v1", credentials=self._creds,
                        cache_discovery=False)
        body = {"startDate": date_from.isoformat(), "endDate": date_to.isoformat(),
                "dimensions": ["date"], "rowLimit": 25000}
        resp = service.searchanalytics().query(siteUrl=site_url, body=body).execute()
        return parse_gsc_response(resp, site_url)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_gsc.py -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add src/hub/connectors/gsc.py tests/test_gsc.py
git commit -m "feat: search console connector"
```

---

### Task 10: YouTube Analytics connector

**Files:**
- Create: `src/hub/connectors/youtube.py`
- Test: `tests/test_youtube.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_youtube.py`:
```python
from hub.connectors.youtube import YOUTUBE_FIELDS, YouTubeConnector, parse_youtube_response

FIXTURE = {
    "columnHeaders": [
        {"name": "day"}, {"name": "views"}, {"name": "likes"},
        {"name": "estimatedMinutesWatched"}, {"name": "subscribersGained"},
    ],
    "rows": [
        ["2026-07-01", 500, 40, 1200, 6],
        ["2026-07-02", 430, 33, 990, 2],
    ],
}


def test_parse_youtube_response():
    rows = parse_youtube_response(FIXTURE, channel_id="mine")
    assert rows[0] == {
        "account_id": "mine", "account_name": "YouTube mine",
        "date": "2026-07-01", "views": 500, "likes": 40,
        "watch_minutes": 1200, "subscribers_gained": 6,
    }


def test_parse_empty():
    assert parse_youtube_response({"rows": []}, channel_id="mine") == []


def test_connector_metadata():
    assert YouTubeConnector.id == "youtube"
    assert set(YOUTUBE_FIELDS.names()) == {
        "date", "views", "likes", "watch_minutes", "subscribers_gained"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_youtube.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement youtube.py**

All YouTube metrics are non-core, so they land in `extras` (per spec: only
date/source/account populate core columns for this source).

`src/hub/connectors/youtube.py`:
```python
from __future__ import annotations

from datetime import date
from typing import Iterable

from hub.connectors.base import BaseConnector, FieldRegistry, FieldSpec
from hub.connectors.google_auth import get_credentials

YOUTUBE_FIELDS = FieldRegistry([
    FieldSpec("date", "day", dimension=True),
    FieldSpec("views", "views"),
    FieldSpec("likes", "likes"),
    FieldSpec("watch_minutes", "estimatedMinutesWatched"),
    FieldSpec("subscribers_gained", "subscribersGained"),
])

_N2U = YOUTUBE_FIELDS.native_to_unified()


def parse_youtube_response(resp: dict, channel_id: str) -> list[dict]:
    headers = [h["name"] for h in resp.get("columnHeaders", [])]
    out = []
    for row in resp.get("rows", []):
        raw = {"account_id": channel_id, "account_name": f"YouTube {channel_id}"}
        for name, value in zip(headers, row):
            raw[_N2U[name]] = value
        out.append(raw)
    return out


class YouTubeConnector(BaseConnector):
    id = "youtube"
    fields = YOUTUBE_FIELDS

    def authenticate(self) -> None:
        self._creds = get_credentials(self.secrets_dir)

    def extract(self, date_from: date, date_to: date) -> Iterable[dict]:
        from googleapiclient.discovery import build

        channel_id = self.settings.options.get("channel_id", "mine")
        ids = "channel==MINE" if channel_id == "mine" else f"channel=={channel_id}"
        service = build("youtubeAnalytics", "v2", credentials=self._creds,
                        cache_discovery=False)
        resp = service.reports().query(
            ids=ids, startDate=date_from.isoformat(), endDate=date_to.isoformat(),
            metrics="views,likes,estimatedMinutesWatched,subscribersGained",
            dimensions="day", sort="day").execute()
        return parse_youtube_response(resp, channel_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_youtube.py -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add src/hub/connectors/youtube.py tests/test_youtube.py
git commit -m "feat: youtube analytics connector"
```


---

### Task 11: Connector catalog

**Files:**
- Create: `src/hub/connectors/catalog.py`
- Test: `tests/test_catalog.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_catalog.py`:
```python
import pytest

from hub.connectors.catalog import ALL_CONNECTORS, build_connector
from hub.connectors.ga4 import GA4Connector
from hub.core.config import ConnectorSettings, HubConfig


def test_catalog_lists_all_five():
    assert set(ALL_CONNECTORS) == {"ga4", "gsc", "youtube", "google_ads", "meta_ads"}


def test_build_configured_connector():
    cfg = HubConfig(connectors={"ga4": ConnectorSettings(options={"property_id": "1"})})
    conn = build_connector("ga4", cfg)
    assert isinstance(conn, GA4Connector)
    assert conn.settings.options["property_id"] == "1"


def test_build_unconfigured_raises():
    with pytest.raises(KeyError, match="not configured"):
        build_connector("ga4", HubConfig())


def test_build_unknown_raises():
    with pytest.raises(KeyError, match="unknown"):
        build_connector("nope", HubConfig())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_catalog.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement catalog.py**

Note: `google_ads` and `meta_ads` modules are created in Tasks 19-20. Until then,
import them lazily so this task passes â€” the catalog maps ids to import paths, not
classes.

`src/hub/connectors/catalog.py`:
```python
from __future__ import annotations

from importlib import import_module

from hub.connectors.base import BaseConnector
from hub.core.config import HubConfig

# id -> (module path, class name). Classes are imported lazily so optional SDK
# dependencies (google-ads, facebook-business) are only needed when configured.
ALL_CONNECTORS: dict[str, tuple[str, str]] = {
    "ga4": ("hub.connectors.ga4", "GA4Connector"),
    "gsc": ("hub.connectors.gsc", "SearchConsoleConnector"),
    "youtube": ("hub.connectors.youtube", "YouTubeConnector"),
    "google_ads": ("hub.connectors.google_ads", "GoogleAdsConnector"),
    "meta_ads": ("hub.connectors.meta_ads", "MetaAdsConnector"),
}


def connector_class(source: str) -> type[BaseConnector]:
    if source not in ALL_CONNECTORS:
        raise KeyError(f"unknown connector: {source!r}")
    module_path, cls_name = ALL_CONNECTORS[source]
    return getattr(import_module(module_path), cls_name)


def build_connector(source: str, config: HubConfig) -> BaseConnector:
    if source not in ALL_CONNECTORS:
        raise KeyError(f"unknown connector: {source!r}")
    if source not in config.connectors:
        raise KeyError(f"connector not configured: {source!r} (add it to config.yaml)")
    cls = connector_class(source)
    return cls(settings=config.connectors[source], secrets_dir=config.secrets_dir)
```

- [ ] **Step 4: Run tests â€” the catalog test for google_ads/meta_ads must not import them**

Run: `python -m pytest tests/test_catalog.py -v`
Expected: 4 PASS (lazy import means the missing modules don't break the catalog test)

- [ ] **Step 5: Commit**

```bash
git add src/hub/connectors/catalog.py tests/test_catalog.py
git commit -m "feat: connector catalog with lazy class loading"
```

---

### Task 12: Sync engine (rolling window, retries, backfill)

**Files:**
- Create: `src/hub/core/sync.py`, `src/hub/core/status.py`
- Test: `tests/test_sync.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_sync.py`:
```python
from datetime import date

import pytest

from hub.core.storage import Storage
from hub.core.sync import backfill_chunks, run_sync
from hub.connectors.base import BaseConnector, FieldRegistry, FieldSpec
from hub.core.config import ConnectorSettings


class FakeConnector(BaseConnector):
    id = "fake"
    fields = FieldRegistry([FieldSpec("date", "date", dimension=True),
                            FieldSpec("clicks", "clicks")])

    def __init__(self, fail_times: int = 0):
        super().__init__(ConnectorSettings(), ".")
        self.fail_times = fail_times
        self.calls = 0

    def authenticate(self):
        pass

    def extract(self, date_from, date_to):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError("api down")
        return [{"date": date_from.isoformat(), "account_id": "a", "clicks": 5}]


@pytest.fixture()
def store(tmp_path):
    return Storage(str(tmp_path / "t.duckdb"))


def test_run_sync_happy_path(store):
    run_sync(store, FakeConnector(), date_from=date(2026, 7, 1), date_to=date(2026, 7, 1))
    assert store.row_counts()["fake"]["rows"] == 1
    assert store.last_runs()["fake"]["status"] == "success"


def test_run_sync_retries_then_succeeds(store, monkeypatch):
    monkeypatch.setattr("hub.core.sync.time.sleep", lambda s: None)
    conn = FakeConnector(fail_times=2)
    run_sync(store, conn, date_from=date(2026, 7, 1), date_to=date(2026, 7, 1))
    assert conn.calls == 3
    assert store.last_runs()["fake"]["status"] == "success"


def test_run_sync_records_error_after_retries(store, monkeypatch):
    monkeypatch.setattr("hub.core.sync.time.sleep", lambda s: None)
    with pytest.raises(RuntimeError):
        run_sync(store, FakeConnector(fail_times=99),
                 date_from=date(2026, 7, 1), date_to=date(2026, 7, 1))
    run = store.last_runs()["fake"]
    assert run["status"] == "error"
    assert "api down" in run["error_message"]


def test_default_window_is_rolling(store):
    conn = FakeConnector()
    run_sync(store, conn, window_days=30)
    run = store.last_runs()["fake"]
    assert (run["finished_at"] is not None)
    assert (date.today() - store.query(["date"], date(2000, 1, 1), date.today())[0]["date"]).days <= 30


def test_backfill_chunks():
    chunks = backfill_chunks(date(2024, 1, 1), date(2024, 6, 30), chunk_days=90)
    assert chunks[0] == (date(2024, 1, 1), date(2024, 3, 30))
    assert chunks[-1][1] == date(2024, 6, 30)
    # chunks cover the range with no gaps/overlaps
    for (a, b), (c, d) in zip(chunks, chunks[1:]):
        assert (c - b).days == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_sync.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement sync.py**

`src/hub/core/sync.py`:
```python
from __future__ import annotations

import time
from datetime import date, timedelta

from hub.connectors.base import BaseConnector
from hub.core.normalizer import normalize
from hub.core.storage import Storage


def run_sync(storage: Storage, connector: BaseConnector,
             date_from: date | None = None, date_to: date | None = None,
             window_days: int = 30, retries: int = 3) -> int:
    """Sync one connector over a date range (default: rolling window ending today).

    Re-fetches and transactionally replaces the whole window because ad platforms
    restate conversions retroactively. Returns rows written."""
    date_to = date_to or date.today()
    date_from = date_from or date_to - timedelta(days=window_days)
    run_id = storage.start_sync(connector.id, date_from, date_to)
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            connector.authenticate()
            raw = list(connector.extract(date_from, date_to))
            rows = normalize(connector.id, raw)
            n = storage.replace_rows(connector.id, date_from, date_to, rows)
            storage.finish_sync(run_id, n, "success")
            return n
        except Exception as exc:  # noqa: BLE001 - anything from an API is retryable
            last_exc = exc
            if attempt < retries - 1:
                time.sleep(2 ** (attempt + 1))
    storage.finish_sync(run_id, 0, "error", error=str(last_exc))
    raise last_exc  # type: ignore[misc]


def backfill_chunks(date_from: date, date_to: date,
                    chunk_days: int = 90) -> list[tuple[date, date]]:
    chunks = []
    start = date_from
    while start <= date_to:
        end = min(start + timedelta(days=chunk_days - 1), date_to)
        chunks.append((start, end))
        start = end + timedelta(days=1)
    return chunks


def backfill(storage: Storage, connector: BaseConnector,
             date_from: date, date_to: date | None = None) -> int:
    date_to = date_to or date.today()
    total = 0
    for start, end in backfill_chunks(date_from, date_to):
        total += run_sync(storage, connector, date_from=start, date_to=end)
    return total
```

- [ ] **Step 4: Implement status.py (shared by API/MCP/CLI)**

`src/hub/core/status.py`:
```python
from __future__ import annotations

from hub.connectors.catalog import ALL_CONNECTORS
from hub.core.config import HubConfig
from hub.core.storage import Storage


def source_statuses(config: HubConfig, storage: Storage) -> list[dict]:
    counts = storage.row_counts()
    runs = storage.last_runs()
    out = []
    for source in ALL_CONNECTORS:
        configured = source in config.connectors
        entry = {
            "source": source,
            "status": "active" if configured else "inactive",
            "rows": counts.get(source, {}).get("rows", 0),
            "latest_date": counts.get(source, {}).get("latest_date"),
            "last_sync": runs.get(source),
        }
        out.append(entry)
    return out
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_sync.py -v`
Expected: 5 PASS

- [ ] **Step 6: Commit**

```bash
git add src/hub/core/sync.py src/hub/core/status.py tests/test_sync.py
git commit -m "feat: sync engine with retries, rolling window, backfill chunking"
```

---

### Task 13: Query API

**Files:**
- Create: `src/hub/api/app.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_api.py`:
```python
from datetime import date

import pytest
from fastapi.testclient import TestClient

from hub.api.app import create_app
from hub.core.config import ConnectorSettings, HubConfig
from hub.core.models import UnifiedRow
from hub.core.storage import Storage

KEY = "test-key"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HUB_API_KEY", KEY)
    store = Storage(str(tmp_path / "t.duckdb"))
    d = date(2026, 7, 1)
    store.replace_rows("ga4", d, d, [
        UnifiedRow(date=d, source="ga4", account_id="p1", campaign="summer",
                   sessions=100, conversions=5)])
    store.replace_rows("gsc", d, d, [
        UnifiedRow(date=d, source="gsc", account_id="s1", clicks=30, impressions=900,
                   extras={"position": 12.0})])
    config = HubConfig(connectors={
        "ga4": ConnectorSettings(options={"property_id": "p1"}),
        "gsc": ConnectorSettings(options={"site_url": "s1"})})
    app = create_app(config, storage=store)
    return TestClient(app)


def auth(params=None):
    return {"params": params or {}, "headers": {"X-API-Key": KEY}}


def test_requires_api_key(client):
    assert client.get("/connectors").status_code == 401
    assert client.get("/connectors", headers={"X-API-Key": KEY}).status_code == 200


def test_list_connectors(client):
    body = client.get("/connectors", headers={"X-API-Key": KEY}).json()
    by_source = {c["source"]: c for c in body}
    assert by_source["ga4"]["status"] == "active"
    assert by_source["ga4"]["rows"] == 1
    assert by_source["meta_ads"]["status"] == "inactive"


def test_fields_endpoint(client):
    body = client.get("/connectors/gsc/fields", headers={"X-API-Key": KEY}).json()
    names = [f["name"] for f in body]
    assert "position" in names and "clicks" in names


def test_data_endpoint_all_sources(client):
    r = client.get("/connectors/all/data", headers={"X-API-Key": KEY},
                   params={"fields": "date,source,clicks,sessions",
                           "date_from": "2026-07-01", "date_to": "2026-07-01"})
    assert r.status_code == 200
    rows = r.json()["data"]
    assert {r["source"] for r in rows} == {"ga4", "gsc"}


def test_data_endpoint_single_source_with_preset(client):
    r = client.get("/connectors/gsc/data", headers={"X-API-Key": KEY},
                   params={"fields": "date,clicks,position", "date_preset": "ytd"})
    assert r.status_code == 200
    assert r.json()["data"][0]["clicks"] == 30


def test_data_endpoint_rejects_unknown_field(client):
    r = client.get("/connectors/gsc/data", headers={"X-API-Key": KEY},
                   params={"fields": "date,bogus_metric"})
    assert r.status_code == 400
    assert "bogus_metric" in r.json()["detail"]


def test_csv_format(client):
    r = client.get("/connectors/gsc/data", headers={"X-API-Key": KEY},
                   params={"fields": "date,clicks", "date_preset": "ytd",
                           "format": "csv"})
    assert r.headers["content-type"].startswith("text/csv")
    assert r.text.splitlines()[0] == "date,clicks"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_api.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement app.py**

`src/hub/api/app.py`:
```python
from __future__ import annotations

import csv
import io
import os
from datetime import date

import duckdb
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import Response

from hub.connectors.catalog import ALL_CONNECTORS, build_connector, connector_class
from hub.core.config import HubConfig
from hub.core.models import CORE_DIMENSIONS, CORE_METRICS
from hub.core.presets import resolve_dates
from hub.core.status import source_statuses
from hub.core.storage import Storage
from hub.core.sync import run_sync


def _check_api_key(request: Request) -> None:
    expected = os.environ.get("HUB_API_KEY", "")
    supplied = request.headers.get("X-API-Key") or request.query_params.get("api_key")
    if not expected or supplied != expected:
        raise HTTPException(status_code=401, detail="invalid or missing API key")


def _known_fields(config: HubConfig, source: str) -> set[str]:
    known = set(CORE_DIMENSIONS) | set(CORE_METRICS)
    sources = ALL_CONNECTORS if source == "all" else [source]
    for s in sources:
        try:
            known |= set(connector_class(s).fields.names())
        except (KeyError, ImportError):
            continue
    return known


def create_app(config: HubConfig, storage: Storage | None = None) -> FastAPI:
    storage = storage or Storage(config.db_path)
    app = FastAPI(title="Marketing Data Hub", dependencies=[Depends(_check_api_key)])

    @app.get("/connectors")
    def list_connectors() -> list[dict]:
        return source_statuses(config, storage)

    @app.get("/connectors/{source}/fields")
    def list_fields(source: str) -> list[dict]:
        if source not in ALL_CONNECTORS:
            raise HTTPException(status_code=404, detail=f"unknown source {source!r}")
        return connector_class(source).fields.to_dict()

    @app.get("/connectors/{source}/data")
    def get_data(source: str,
                 fields: str = Query(...),
                 date_from: date | None = None,
                 date_to: date | None = None,
                 date_preset: str | None = None,
                 campaign: str | None = None,
                 account_id: str | None = None,
                 format: str = "json"):
        if source != "all" and source not in ALL_CONNECTORS:
            raise HTTPException(status_code=404, detail=f"unknown source {source!r}")
        field_list = [f.strip() for f in fields.split(",") if f.strip()]
        unknown = [f for f in field_list if f not in _known_fields(config, source)]
        if unknown:
            raise HTTPException(status_code=400,
                                detail=f"unknown fields: {', '.join(unknown)}")
        try:
            df, dt = resolve_dates(date_preset, date_from, date_to)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        filters = {}
        if campaign:
            filters["campaign"] = campaign
        if account_id:
            filters["account_id"] = account_id
        sources = None if source == "all" else [source]
        try:
            rows = storage.query(field_list, df, dt, sources=sources, filters=filters)
        except duckdb.IOException as exc:
            raise HTTPException(status_code=503, detail=f"database unavailable: {exc}")
        if format == "csv":
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=field_list)
            writer.writeheader()
            writer.writerows(rows)
            return Response(content=buf.getvalue(), media_type="text/csv")
        return {"date_from": df.isoformat(), "date_to": dt.isoformat(), "data": rows}

    @app.post("/connectors/{source}/sync")
    def trigger_sync(source: str, background: BackgroundTasks) -> dict:
        try:
            connector = build_connector(source, config)
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        window = config.connectors[source].window_days
        background.add_task(run_sync, storage, connector, None, None, window)
        return {"status": "started", "source": source}

    return app
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_api.py -v`
Expected: 7 PASS

Note: JSON serialization of `date` values in `data` rows is handled by FastAPI's
encoder. If a test fails on date encoding, convert in `get_data` with
`rows = [{k: (v.isoformat() if isinstance(v, date) else v) for k, v in r.items()} for r in rows]`.

- [ ] **Step 5: Commit**

```bash
git add src/hub/api/app.py tests/test_api.py
git commit -m "feat: windsor-style query API"
```

---

### Task 14: CSV export destination

**Files:**
- Create: `src/hub/destinations/csv_export.py`
- Test: `tests/test_csv_export.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_csv_export.py`:
```python
from datetime import date
from pathlib import Path

from hub.core.config import ExportConfig
from hub.core.models import UnifiedRow
from hub.core.storage import Storage
from hub.destinations.csv_export import run_export


def test_run_export_writes_csv(tmp_path: Path):
    store = Storage(str(tmp_path / "t.duckdb"))
    d = date.today()
    store.replace_rows("ga4", d, d, [
        UnifiedRow(date=d, source="ga4", account_id="p1", clicks=7, spend=1.5)])
    cfg = ExportConfig(name="overview", fields=["date", "source", "clicks", "spend"],
                       date_preset="last_7d")
    out = run_export(store, cfg, exports_dir=tmp_path / "exports")
    assert out == tmp_path / "exports" / "overview.csv"
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert lines[0] == "date,source,clicks,spend"
    assert lines[1].endswith("ga4,7,1.5")


def test_export_respects_source_filter(tmp_path: Path):
    store = Storage(str(tmp_path / "t.duckdb"))
    d = date.today()
    store.replace_rows("ga4", d, d, [UnifiedRow(date=d, source="ga4", account_id="a", clicks=1)])
    store.replace_rows("gsc", d, d, [UnifiedRow(date=d, source="gsc", account_id="b", clicks=2)])
    cfg = ExportConfig(name="gsc_only", fields=["date", "clicks"],
                       sources=["gsc"], date_preset="last_7d")
    out = run_export(store, cfg, exports_dir=tmp_path)
    assert out.read_text(encoding="utf-8").strip().splitlines()[1].endswith(",2")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_csv_export.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement csv_export.py**

`src/hub/destinations/csv_export.py`:
```python
from __future__ import annotations

import csv
from pathlib import Path

from hub.core.config import ExportConfig
from hub.core.presets import resolve_dates
from hub.core.storage import Storage


def run_export(storage: Storage, export: ExportConfig,
               exports_dir: str | Path) -> Path:
    exports_dir = Path(exports_dir)
    exports_dir.mkdir(parents=True, exist_ok=True)
    date_from, date_to = resolve_dates(export.date_preset)
    rows = storage.query(export.fields, date_from, date_to, sources=export.sources)
    out_path = exports_dir / (export.filename or f"{export.name}.csv")
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=export.fields)
        writer.writeheader()
        writer.writerows(rows)
    return out_path
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_csv_export.py -v`
Expected: 2 PASS

- [ ] **Step 5: Commit**

```bash
git add src/hub/destinations/csv_export.py tests/test_csv_export.py
git commit -m "feat: csv export destination"
```

---

### Task 15: CLI (sync, backfill, status, doctor, export, serve, mcp)

**Files:**
- Create: `src/hub/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_cli.py`:
```python
from pathlib import Path

from typer.testing import CliRunner

from hub.cli import app

runner = CliRunner()


def write_config(tmp_path: Path) -> Path:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        f"db_path: {(tmp_path / 'hub.duckdb').as_posix()}\n"
        f"secrets_dir: {(tmp_path / 'secrets').as_posix()}\n"
        f"exports_dir: {(tmp_path / 'exports').as_posix()}\n"
        "connectors: {}\n",
        encoding="utf-8")
    return cfg


def test_status_on_empty_db(tmp_path):
    cfg = write_config(tmp_path)
    result = runner.invoke(app, ["status", "--config", str(cfg)])
    assert result.exit_code == 0
    assert "ga4" in result.output
    assert "inactive" in result.output


def test_doctor_with_no_connectors(tmp_path):
    cfg = write_config(tmp_path)
    result = runner.invoke(app, ["doctor", "--config", str(cfg)])
    assert result.exit_code == 0
    assert "No connectors configured" in result.output


def test_sync_unconfigured_source_fails_cleanly(tmp_path):
    cfg = write_config(tmp_path)
    result = runner.invoke(app, ["sync", "ga4", "--config", str(cfg)])
    assert result.exit_code == 1
    assert "not configured" in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement cli.py**

`src/hub/cli.py`:
```python
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import typer

from hub.core.config import HubConfig, load_config

app = typer.Typer(help="Marketing Data Hub â€” personal Windsor.ai replica")

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
    _run_exports(cfg, storage)
    raise typer.Exit(1 if failures else 0)


@app.command()
def backfill(source: str, config: str = CONFIG_OPT,
             from_: str = typer.Option(..., "--from", help="YYYY-MM-DD"),
             to: str | None = typer.Option(None, "--to", help="YYYY-MM-DD")):
    """Backfill history in <=90-day chunks."""
    from hub.connectors.catalog import build_connector
    from hub.core.storage import Storage
    from hub.core.sync import backfill as run_backfill

    cfg = _load(config)
    storage = Storage(cfg.db_path)
    connector = build_connector(source, cfg)
    date_from = datetime.strptime(from_, "%Y-%m-%d").date()
    date_to = datetime.strptime(to, "%Y-%m-%d").date() if to else None
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
```

Note: `build_scheduler` (Task 16) and `build_mcp` (Task 17) don't exist yet; they
are imported lazily inside their commands, so the tests in this task still pass.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_cli.py -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add src/hub/cli.py tests/test_cli.py
git commit -m "feat: hub CLI (sync, backfill, status, doctor, export, serve, mcp)"
```


---

### Task 16: Scheduler

**Files:**
- Create: `src/hub/scheduler/runner.py`
- Test: `tests/test_scheduler.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_scheduler.py`:
```python
from hub.core.config import ConnectorSettings, HubConfig
from hub.core.storage import Storage
from hub.scheduler.runner import build_scheduler


def test_one_job_per_configured_connector(tmp_path):
    cfg = HubConfig(
        db_path=str(tmp_path / "t.duckdb"),
        connectors={
            "ga4": ConnectorSettings(schedule="0 6 * * *", options={"property_id": "1"}),
            "gsc": ConnectorSettings(schedule="30 6 * * *", options={"site_url": "x"}),
        })
    storage = Storage(cfg.db_path)
    scheduler = build_scheduler(cfg, storage)
    jobs = {j.id for j in scheduler.get_jobs()}
    assert jobs == {"sync_ga4", "sync_gsc"}


def test_no_connectors_no_jobs(tmp_path):
    cfg = HubConfig(db_path=str(tmp_path / "t.duckdb"))
    scheduler = build_scheduler(cfg, Storage(cfg.db_path))
    assert scheduler.get_jobs() == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_scheduler.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement runner.py**

`src/hub/scheduler/runner.py`:
```python
from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from hub.core.config import HubConfig
from hub.core.storage import Storage


def _sync_job(config: HubConfig, storage: Storage, source: str) -> None:
    from hub.connectors.catalog import build_connector
    from hub.core.sync import run_sync
    from hub.destinations.csv_export import run_export

    try:
        connector = build_connector(source, config)
        run_sync(storage, connector,
                 window_days=config.connectors[source].window_days)
        for exp in config.exports:
            if exp.sources is None or source in exp.sources:
                run_export(storage, exp, config.exports_dir)
    except Exception as exc:  # noqa: BLE001 - scheduler must never crash the process
        print(f"[scheduler] sync {source} failed: {exc}")


def build_scheduler(config: HubConfig, storage: Storage) -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    for source, settings in config.connectors.items():
        scheduler.add_job(
            _sync_job,
            CronTrigger.from_crontab(settings.schedule),
            args=[config, storage, source],
            id=f"sync_{source}",
            max_instances=1,
            coalesce=True,
        )
    return scheduler
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_scheduler.py -v`
Expected: 2 PASS

- [ ] **Step 5: Commit**

```bash
git add src/hub/scheduler/runner.py tests/test_scheduler.py
git commit -m "feat: cron scheduler with post-sync exports"
```

---

### Task 17: MCP server

**Files:**
- Modify: `src/hub/core/storage.py` (add `close()`)
- Create: `src/hub/mcp/server.py`
- Test: `tests/test_mcp.py`

Note: the MCP process opens DuckDB read-only. DuckDB allows multiple read-only
processes, but a read-only connection cannot coexist with the `serve` process's
write connection. For v1 this is acceptable for personal use: tools surface the
lock error as a readable message ("stop `hub serve` or retry"). `trigger_sync`
shells out to the CLI so this process never writes.

- [ ] **Step 1: Write the failing tests**

`tests/test_mcp.py`:
```python
import asyncio
from datetime import date

from hub.core.config import ConnectorSettings, HubConfig
from hub.core.models import UnifiedRow
from hub.core.storage import Storage
from hub.mcp.server import build_mcp


def make_config(tmp_path):
    return HubConfig(
        db_path=str(tmp_path / "t.duckdb"),
        connectors={"gsc": ConnectorSettings(options={"site_url": "x"})})


def seed(cfg):
    store = Storage(cfg.db_path)
    d = date.today()
    store.replace_rows("gsc", d, d, [
        UnifiedRow(date=d, source="gsc", account_id="x", clicks=12, impressions=300)])
    store.close()


def test_build_mcp_registers_tools(tmp_path):
    cfg = make_config(tmp_path)
    seed(cfg)
    mcp = build_mcp(cfg)
    tools = asyncio.run(mcp.get_tools())
    assert {"list_sources", "list_fields", "query_metrics", "trigger_sync"} <= set(tools)


def test_query_metrics_tool_logic(tmp_path):
    cfg = make_config(tmp_path)
    seed(cfg)
    mcp = build_mcp(cfg)
    result = asyncio.run(mcp._call_query_metrics(  # exposed for tests
        fields=["date", "clicks"], date_preset="last_7d"))
    assert result["rows"][0]["clicks"] == 12
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_mcp.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Add Storage.close()**

Append to the `Storage` class in `src/hub/core/storage.py`:
```python
    def close(self) -> None:
        self.conn.close()
```

- [ ] **Step 4: Implement server.py**

`src/hub/mcp/server.py`:
```python
from __future__ import annotations

import subprocess
import sys
from datetime import date
from pathlib import Path

from fastmcp import FastMCP

from hub.connectors.catalog import connector_class
from hub.core.config import HubConfig
from hub.core.presets import resolve_dates
from hub.core.status import source_statuses
from hub.core.storage import Storage


def build_mcp(config: HubConfig, config_path: str = "config.yaml") -> FastMCP:
    mcp = FastMCP("marketing-data-hub")

    if not Path(config.db_path).exists():
        Storage(config.db_path).close()  # create schema so read-only open works
    storage = Storage(config.db_path, read_only=True)

    def _query_metrics(fields: list[str], date_preset: str | None = None,
                       date_from: str | None = None, date_to: str | None = None,
                       source: str | None = None, campaign: str | None = None) -> dict:
        df, dt = resolve_dates(
            date_preset,
            date.fromisoformat(date_from) if date_from else None,
            date.fromisoformat(date_to) if date_to else None)
        filters = {"campaign": campaign} if campaign else None
        rows = storage.query(fields, df, dt,
                             sources=[source] if source else None, filters=filters)
        return {"date_from": df.isoformat(), "date_to": dt.isoformat(),
                "rows": [{k: (v.isoformat() if isinstance(v, date) else v)
                          for k, v in r.items()} for r in rows]}

    # exposed for tests
    async def _call_query_metrics(**kwargs) -> dict:
        return _query_metrics(**kwargs)
    mcp._call_query_metrics = _call_query_metrics  # type: ignore[attr-defined]

    @mcp.tool()
    def list_sources() -> list[dict]:
        """List marketing data sources with sync status, row counts, freshness."""
        return source_statuses(config, storage)

    @mcp.tool()
    def list_fields(source: str) -> list[dict]:
        """List queryable fields for one source (ga4, gsc, youtube, google_ads, meta_ads)."""
        return connector_class(source).fields.to_dict()

    @mcp.tool()
    def query_metrics(fields: list[str], date_preset: str | None = None,
                      date_from: str | None = None, date_to: str | None = None,
                      source: str | None = None, campaign: str | None = None) -> dict:
        """Query unified marketing metrics, e.g. fields=["date","source","clicks","spend"]
        with date_preset one of last_7d/last_30d/last_90d/this_month/last_month/ytd."""
        try:
            return _query_metrics(fields, date_preset, date_from, date_to, source, campaign)
        except Exception as exc:  # noqa: BLE001 - return readable errors to the model
            return {"error": str(exc)}

    @mcp.tool()
    def trigger_sync(source: str) -> str:
        """Run a sync now for one source (or 'all'). Uses the CLI so this
        process stays read-only."""
        proc = subprocess.run(
            [sys.executable, "-m", "hub.cli", "sync", source, "--config", config_path],
            capture_output=True, text=True, timeout=900)
        return (proc.stdout + proc.stderr).strip()

    return mcp
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_mcp.py -v`
Expected: 2 PASS

If `mcp.get_tools()` has a different shape in the installed fastmcp version, check
`fastmcp` docs: in 2.x it is `async def get_tools() -> dict[str, Tool]`. Adjust the
test to the installed version's accessor, not the implementation.

- [ ] **Step 6: Commit**

```bash
git add src/hub/core/storage.py src/hub/mcp/server.py tests/test_mcp.py
git commit -m "feat: MCP server for Claude (list/query/sync tools)"
```

---

### Task 18: Google Ads connector (dormant)

**Files:**
- Create: `src/hub/connectors/google_ads.py`
- Test: `tests/test_google_ads.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_google_ads.py`:
```python
import pytest

from hub.connectors.base import AuthError
from hub.connectors.google_ads import (GOOGLE_ADS_FIELDS, GoogleAdsConnector,
                                       parse_google_ads_rows)
from hub.core.config import ConnectorSettings

FIXTURE = [
    {"segments.date": "2026-07-01", "campaign.id": 111, "campaign.name": "Brand",
     "metrics.impressions": 1000, "metrics.clicks": 50,
     "metrics.cost_micros": 12_500_000, "metrics.conversions": 3.0,
     "metrics.conversions_value": 240.0},
]


def test_parse_google_ads_rows():
    rows = parse_google_ads_rows(FIXTURE, customer_id="123-456")
    assert rows[0] == {
        "account_id": "123-456", "account_name": "Google Ads 123-456",
        "date": "2026-07-01", "campaign_id": "111", "campaign": "Brand",
        "impressions": 1000, "clicks": 50, "spend": 12.5,
        "conversions": 3.0, "conversion_value": 240.0,
    }


def test_connector_metadata():
    assert GoogleAdsConnector.id == "google_ads"
    assert "spend" in GOOGLE_ADS_FIELDS.names()


def test_authenticate_without_dev_token_raises_hint():
    conn = GoogleAdsConnector(ConnectorSettings(options={"customer_id": "1"}), ".")
    with pytest.raises(AuthError) as exc:
        conn.authenticate()
    assert "developer_token" in exc.value.hint
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_google_ads.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement google_ads.py**

`src/hub/connectors/google_ads.py`:
```python
from __future__ import annotations

import json
from datetime import date
from typing import Iterable

from hub.connectors.base import AuthError, BaseConnector, FieldRegistry, FieldSpec

GOOGLE_ADS_FIELDS = FieldRegistry([
    FieldSpec("date", "segments.date", dimension=True),
    FieldSpec("campaign_id", "campaign.id", dimension=True),
    FieldSpec("campaign", "campaign.name", dimension=True),
    FieldSpec("impressions", "metrics.impressions"),
    FieldSpec("clicks", "metrics.clicks"),
    FieldSpec("spend", "metrics.cost_micros", description="cost_micros / 1e6"),
    FieldSpec("conversions", "metrics.conversions"),
    FieldSpec("conversion_value", "metrics.conversions_value"),
])

_GAQL = """
    SELECT segments.date, campaign.id, campaign.name, metrics.impressions,
           metrics.clicks, metrics.cost_micros, metrics.conversions,
           metrics.conversions_value
    FROM campaign
    WHERE segments.date BETWEEN '{start}' AND '{end}'
"""


def parse_google_ads_rows(rows: list[dict], customer_id: str) -> list[dict]:
    out = []
    for row in rows:
        out.append({
            "account_id": customer_id,
            "account_name": f"Google Ads {customer_id}",
            "date": row["segments.date"],
            "campaign_id": str(row["campaign.id"]),
            "campaign": row["campaign.name"],
            "impressions": row["metrics.impressions"],
            "clicks": row["metrics.clicks"],
            "spend": row["metrics.cost_micros"] / 1_000_000,
            "conversions": row["metrics.conversions"],
            "conversion_value": row["metrics.conversions_value"],
        })
    return out


class GoogleAdsConnector(BaseConnector):
    id = "google_ads"
    fields = GOOGLE_ADS_FIELDS

    def authenticate(self) -> None:
        opts = self.settings.options
        if not opts.get("developer_token"):
            raise AuthError(
                "Google Ads connector is not activated.",
                hint=("Apply for a developer_token at ads.google.com > Tools > "
                      "API Center, then add developer_token, customer_id and "
                      "login_customer_id under connectors.google_ads.options "
                      "in config.yaml."))
        token_path = self.secrets_dir / "google_token.json"
        client_path = self.secrets_dir / "google_client.json"
        if not token_path.exists() or not client_path.exists():
            raise AuthError(
                "Google OAuth files missing.",
                hint="Run a sync of ga4/gsc first to create secrets/google_token.json.")
        token = json.loads(token_path.read_text(encoding="utf-8"))
        client = json.loads(client_path.read_text(encoding="utf-8"))
        installed = client.get("installed") or client.get("web") or {}
        self._ads_config = {
            "developer_token": opts["developer_token"],
            "client_id": installed.get("client_id") or token.get("client_id"),
            "client_secret": installed.get("client_secret") or token.get("client_secret"),
            "refresh_token": token["refresh_token"],
            "login_customer_id": str(opts.get("login_customer_id", opts["customer_id"])).replace("-", ""),
            "use_proto_plus": True,
        }

    def extract(self, date_from: date, date_to: date) -> Iterable[dict]:
        from google.ads.googleads.client import GoogleAdsClient

        customer_id = str(self.settings.options["customer_id"]).replace("-", "")
        client = GoogleAdsClient.load_from_dict(self._ads_config)
        service = client.get_service("GoogleAdsService")
        query = _GAQL.format(start=date_from.isoformat(), end=date_to.isoformat())
        flat_rows = []
        for batch in service.search_stream(customer_id=customer_id, query=query):
            for row in batch.results:
                flat_rows.append({
                    "segments.date": row.segments.date,
                    "campaign.id": row.campaign.id,
                    "campaign.name": row.campaign.name,
                    "metrics.impressions": row.metrics.impressions,
                    "metrics.clicks": row.metrics.clicks,
                    "metrics.cost_micros": row.metrics.cost_micros,
                    "metrics.conversions": row.metrics.conversions,
                    "metrics.conversions_value": row.metrics.conversions_value,
                })
        return parse_google_ads_rows(flat_rows, self.settings.options["customer_id"])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_google_ads.py -v`
Expected: 3 PASS (no google-ads SDK needed â€” it is only imported inside extract)

- [ ] **Step 5: Commit**

```bash
git add src/hub/connectors/google_ads.py tests/test_google_ads.py
git commit -m "feat: google ads connector (dormant until developer token)"
```

---

### Task 19: Meta Ads connector (dormant)

**Files:**
- Create: `src/hub/connectors/meta_ads.py`
- Test: `tests/test_meta_ads.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_meta_ads.py`:
```python
import pytest

from hub.connectors.base import AuthError
from hub.connectors.meta_ads import META_FIELDS, MetaAdsConnector, parse_meta_insights
from hub.core.config import ConnectorSettings

FIXTURE = [
    {"date_start": "2026-07-01", "campaign_id": "c1", "campaign_name": "Retarget",
     "impressions": "2000", "clicks": "80", "spend": "45.20",
     "actions": [{"action_type": "purchase", "value": "4"},
                 {"action_type": "link_click", "value": "70"}]},
]


def test_parse_meta_insights():
    rows = parse_meta_insights(FIXTURE, account_id="act_1")
    assert rows[0] == {
        "account_id": "act_1", "account_name": "Meta act_1",
        "date": "2026-07-01", "campaign_id": "c1", "campaign": "Retarget",
        "impressions": "2000", "clicks": "80", "spend": "45.20",
        "conversions": 4.0,
    }


def test_parse_custom_conversion_actions():
    rows = parse_meta_insights(FIXTURE, account_id="act_1",
                               conversion_actions=["link_click"])
    assert rows[0]["conversions"] == 70.0


def test_connector_metadata():
    assert MetaAdsConnector.id == "meta_ads"
    assert "spend" in META_FIELDS.names()


def test_authenticate_without_token_raises_hint():
    conn = MetaAdsConnector(ConnectorSettings(options={"ad_account_id": "act_1"}), ".")
    with pytest.raises(AuthError) as exc:
        conn.authenticate()
    assert "access_token" in exc.value.hint
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_meta_ads.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement meta_ads.py**

`src/hub/connectors/meta_ads.py`:
```python
from __future__ import annotations

from datetime import date
from typing import Iterable

from hub.connectors.base import AuthError, BaseConnector, FieldRegistry, FieldSpec

META_FIELDS = FieldRegistry([
    FieldSpec("date", "date_start", dimension=True),
    FieldSpec("campaign_id", "campaign_id", dimension=True),
    FieldSpec("campaign", "campaign_name", dimension=True),
    FieldSpec("impressions", "impressions"),
    FieldSpec("clicks", "clicks"),
    FieldSpec("spend", "spend"),
    FieldSpec("conversions", "actions",
              description="sum of configured conversion_actions"),
])

DEFAULT_CONVERSION_ACTIONS = ["purchase", "lead", "offsite_conversion.fb_pixel_purchase"]


def parse_meta_insights(rows: list[dict], account_id: str,
                        conversion_actions: list[str] | None = None) -> list[dict]:
    actions_wanted = conversion_actions or DEFAULT_CONVERSION_ACTIONS
    out = []
    for row in rows:
        conversions = sum(
            float(a["value"]) for a in row.get("actions", [])
            if a.get("action_type") in actions_wanted)
        out.append({
            "account_id": account_id, "account_name": f"Meta {account_id}",
            "date": row["date_start"],
            "campaign_id": row.get("campaign_id"),
            "campaign": row.get("campaign_name"),
            "impressions": row.get("impressions"),
            "clicks": row.get("clicks"),
            "spend": row.get("spend"),
            "conversions": conversions,
        })
    return out


class MetaAdsConnector(BaseConnector):
    id = "meta_ads"
    fields = META_FIELDS

    def authenticate(self) -> None:
        opts = self.settings.options
        if not opts.get("access_token") or not opts.get("ad_account_id"):
            raise AuthError(
                "Meta Ads connector is not activated.",
                hint=("Create a Meta app at developers.facebook.com, generate a "
                      "long-lived access_token with ads_read permission, and add "
                      "access_token + ad_account_id (act_...) under "
                      "connectors.meta_ads.options in config.yaml."))

    def extract(self, date_from: date, date_to: date) -> Iterable[dict]:
        from facebook_business.adobjects.adaccount import AdAccount
        from facebook_business.api import FacebookAdsApi

        opts = self.settings.options
        FacebookAdsApi.init(access_token=opts["access_token"])
        account = AdAccount(opts["ad_account_id"])
        insights = account.get_insights(
            fields=["campaign_id", "campaign_name", "impressions", "clicks",
                    "spend", "actions"],
            params={"level": "campaign", "time_increment": 1,
                    "time_range": {"since": date_from.isoformat(),
                                   "until": date_to.isoformat()}})
        rows = [dict(i) for i in insights]
        return parse_meta_insights(rows, opts["ad_account_id"],
                                   opts.get("conversion_actions"))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_meta_ads.py -v`
Expected: 4 PASS (facebook-business only imported inside extract)

- [ ] **Step 5: Commit**

```bash
git add src/hub/connectors/meta_ads.py tests/test_meta_ads.py
git commit -m "feat: meta ads connector (dormant until app credentials)"
```

---

### Task 20: README + full verification

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write README.md**

```markdown
# Marketing Data Hub

Personal Windsor.ai-style pipeline: pulls GA4, Search Console, YouTube (and, once
activated, Google Ads + Meta Ads) into a unified DuckDB schema, queryable via a
Windsor-style REST API, scheduled CSV exports, and an MCP server for Claude.

## Setup

1. `python -m pip install -e ".[dev]"`
2. Copy `config.yaml.example` â†’ `config.yaml`; fill in your GA4 `property_id`
   and Search Console `site_url`.
3. Copy `.env.example` â†’ `.env`; set a random `HUB_API_KEY`.
4. Google Cloud Console â†’ create a project â†’ enable **Google Analytics Data API**,
   **Search Console API**, **YouTube Analytics API** â†’ create an **OAuth client
   (Desktop app)** â†’ download JSON to `secrets/google_client.json`.
5. `hub doctor` â€” first run opens a browser to authorize; then all checks go green.

## Daily use

| Command | What it does |
|---|---|
| `hub sync all` | sync every configured source (rolling 30-day window) |
| `hub backfill ga4 --from 2024-01-01` | load history in 90-day chunks |
| `hub status` | row counts + last sync per source |
| `hub serve` | query API on 127.0.0.1:8000 + cron scheduler |
| `hub export all` | write configured CSVs to exports/ |
| `hub mcp` | MCP server (stdio) for Claude |

## Query API

```
GET /connectors/all/data?fields=date,source,clicks,spend&date_preset=last_30d
X-API-Key: <HUB_API_KEY>
```
`format=csv` for CSV. `/connectors` lists sources; `/connectors/{source}/fields`
lists fields.

## Claude MCP

`claude mcp add marketing-hub -- python -m hub.cli mcp --config <absolute-path>/config.yaml`
Then ask Claude: "How did my campaigns do last week?"

## Activating the ad connectors

- **Google Ads:** apply for a developer token (API Center), then uncomment
  `google_ads` in config.yaml and fill options.
- **Meta Ads:** create a Meta app, generate a long-lived token with `ads_read`,
  uncomment `meta_ads` and fill options.
```

- [ ] **Step 2: Run the full test suite**

Run: `python -m pytest -v`
Expected: ALL PASS (â‰ˆ45 tests)

- [ ] **Step 3: Smoke-check the CLI entry point**

Run: `hub --help`
Expected: lists sync, backfill, status, doctor, export, serve, mcp

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: README with setup, usage, and activation guide"
```

---

## Post-implementation (manual, requires the user)

These need the user's accounts and cannot be done by the executor:

1. Create the Google Cloud project + OAuth client, enable the three APIs, save
   `secrets/google_client.json`, run `hub doctor`, complete the browser consent.
2. Fill real `property_id` / `site_url` in config.yaml.
3. `hub backfill all --from <campaign start>` then `hub serve`.
4. Register the MCP server in Claude.
5. When the Google Ads developer token and Meta app are approved, activate those
   connector sections and re-run `hub doctor`.

