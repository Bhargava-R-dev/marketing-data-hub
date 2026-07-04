# Marketing Data Hub — Personal Windsor.ai Replica

**Date:** 2026-07-04
**Status:** Approved design
**Owner:** Bhargava

## Purpose

A personal, self-hosted replica of Windsor.ai's architecture: pull marketing/analytics
data from platform APIs into a unified local schema, and expose it through a
Windsor-style query API, scheduled CSV exports, and an MCP server usable from Claude.

The user runs real ad campaigns. Real data flows from day one for the Google
connectors that need no gated approval; ad-platform connectors are code-complete and
activate when developer credentials arrive.

## Scope

**In scope (v1):**
- Connector framework (plugin base class + OAuth helper + field registry)
- Live connectors: Google Analytics 4, Google Search Console, YouTube Analytics
- Dormant connectors (code-complete, credential-gated): Google Ads, Meta Ads
- DuckDB storage with unified schema + sync bookkeeping
- FastAPI query API (Windsor-style `fields=` querying, JSON/CSV output)
- APScheduler-based sync scheduling + CLI backfills
- CSV export destination
- FastMCP server for Claude
- `doctor` CLI for auth/health checks

**Out of scope (v1):**
- LinkedIn Ads, TikTok Ads (partner-gated APIs; add later as plugins)
- Cloud warehouse destinations (BigQuery/Snowflake)
- Web dashboard UI
- Write-back / campaign management (Windsor MCP "actions")
- Multi-user auth

## Architecture

```
┌─────────────── Connectors (plugins) ───────────────┐
│ GA4 │ Search Console │ YouTube │ Google Ads* │ Meta*│  * credential-gated
└────────────────────┬────────────────────────────────┘
                     ▼
              Normalizer (field registry → unified schema)
                     ▼
              DuckDB (metrics + sync_runs)
                     ▼
    ┌────────────────┼──────────────────┐
    ▼                ▼                  ▼
FastAPI query API   CSV exporter    MCP server (Claude)
                     ▲
              APScheduler (scheduled syncs, backfills)
```

- One Python process runs FastAPI + APScheduler.
- The MCP server is a separate small process reading the same DuckDB file
  (read-only connection to avoid writer conflicts).
- Language: Python 3.11+. Key deps: `fastapi`, `uvicorn`, `duckdb`, `apscheduler`,
  `fastmcp`, `pydantic`, official platform SDKs (`google-analytics-data`,
  `google-api-python-client`, `google-ads`, `facebook-business`).

## Project layout

```
marketing-data-hub/
  config.yaml              # connectors, schedules, exports (no secrets)
  .env                     # API key for query API
  secrets/                 # OAuth client + token files (gitignored)
  src/hub/
    connectors/
      base.py              # BaseConnector ABC + FieldRegistry
      google_auth.py       # shared Google OAuth helper
      ga4.py, gsc.py, youtube.py, google_ads.py, meta_ads.py
    core/
      normalizer.py        # native rows → unified rows
      storage.py           # DuckDB access layer (writes, queries, sync log)
      models.py            # pydantic models: UnifiedRow, SyncRun, config schemas
    api/
      app.py               # FastAPI app + endpoints
    scheduler/
      runner.py            # APScheduler wiring, sync orchestration
    destinations/
      csv_export.py
    mcp/
      server.py            # FastMCP server
    cli.py                 # hub sync / backfill / doctor / serve / mcp
  tests/
    fixtures/              # recorded API responses per connector
    test_normalizer.py, test_storage.py, test_api.py, test_connectors.py
  exports/                 # CSV output (gitignored)
  data/hub.duckdb          # database (gitignored)
```

## Unified data model

**`metrics` table (DuckDB):**

| column           | type    | notes                                   |
|------------------|---------|-----------------------------------------|
| date             | DATE    | reporting date                          |
| source           | VARCHAR | connector id: `ga4`, `gsc`, `youtube`…  |
| account_id       | VARCHAR | property/site/channel/account id        |
| account_name     | VARCHAR |                                         |
| campaign_id      | VARCHAR | nullable (analytics sources)            |
| campaign         | VARCHAR | nullable                                |
| impressions      | BIGINT  | nullable                                |
| clicks           | BIGINT  | nullable                                |
| spend            | DOUBLE  | nullable; account currency              |
| conversions      | DOUBLE  | nullable                                |
| conversion_value | DOUBLE  | nullable                                |
| sessions         | BIGINT  | nullable                                |
| users            | BIGINT  | nullable                                |
| extras           | JSON    | source-specific fields (position, watch_time, ctr…) |

Grain: one row per (date, source, account, campaign-or-dimension-combo). Sources
without campaigns (GSC) use their natural dimension (e.g., site totals per day in
core columns; query/page breakdowns live in `extras`-bearing rows — the connector's
field registry defines the grain it emits).

**`sync_runs` table:** id, source, started_at, finished_at, date_from, date_to,
rows_written, status (`success`/`error`), error_message.

**Field registry:** each connector declares `FieldSpec(unified_name, native_name,
type, is_dimension)` entries. The registry drives (a) normalization, (b) the
`/connectors/{source}/fields` endpoint, (c) MCP `list_fields`. Unified core fields
are identical across connectors; anything unmapped goes to `extras`.

## Connector framework

```python
class BaseConnector(ABC):
    id: str                       # "ga4"
    fields: FieldRegistry

    def authenticate(self) -> None: ...          # raises AuthError with fix hint
    def extract(self, date_from: date, date_to: date) -> Iterator[dict]: ...
```

- **Google OAuth helper:** one OAuth client (Desktop app) covering GA4, GSC,
  YouTube Analytics, and Google Ads scopes. Browser consent flow with localhost
  redirect on first run; refresh token stored in `secrets/google_token.json`.
- **GA4:** Analytics Data API `runReport` — dimensions: date, sessionCampaignName;
  metrics: sessions, totalUsers, conversions, purchaseRevenue.
- **Search Console:** Search Analytics API — date dimension; clicks, impressions,
  ctr, position (ctr/position → extras).
- **YouTube Analytics:** day dimension; views→impressions-analog kept in extras,
  estimatedMinutesWatched, subscribersGained in extras; views/likes mapped per
  registry.
- **Google Ads (dormant):** GAQL query per day/campaign — impressions, clicks,
  cost_micros→spend, conversions, conversions_value. Activated by adding
  `developer_token` + `login_customer_id` to config.
- **Meta Ads (dormant):** Insights API, campaign level, daily breakdown —
  impressions, clicks, spend, actions→conversions. Uses async report jobs via
  `facebook-business` SDK. Activated by adding app id/secret + long-lived token.

A connector is "configured" when its section exists in `config.yaml` with valid
credentials; unconfigured connectors are listed as `inactive` everywhere, never
errors.

## Sync semantics

- **Rolling re-fetch window:** each scheduled sync re-pulls the last N days
  (default 30, per-connector configurable) and replaces those rows — ad platforms
  restate conversions retroactively.
- **Replace = transactional delete+insert** for (source, date range) in one DuckDB
  transaction; a failed sync never leaves partial data.
- **Backfill:** `hub backfill <source|all> --from 2024-01-01 [--to ...]` chunks the
  range into ≤90-day windows to respect API limits.
- **Retries:** exponential backoff (3 attempts) on 429/5xx; rate-limit sleep hints
  honored where APIs provide them. Terminal failures recorded in `sync_runs`.

## Query API

`uvicorn`-served FastAPI, bound to `127.0.0.1`, API key via `X-API-Key` header or
`api_key` query param (key in `.env`).

- `GET /connectors` — sources with status (active/inactive), last sync, row counts.
- `GET /connectors/{source}/fields` — unified + extras fields available.
- `GET /connectors/{source|all}/data` — params:
  - `fields=date,source,campaign,clicks,spend` (required; validated against registry)
  - `date_from`/`date_to` or `date_preset` (`last_7d`, `last_30d`, `last_90d`,
    `this_month`, `last_month`, `ytd`)
  - simple equality filters: `campaign=`, `account_id=`, `source=` (on /all)
  - `format=json|csv` (default json)
  - Aggregation: rows are grouped by the requested dimension fields with metrics
    summed — matching Windsor's behavior where `fields` shapes the result grain.
- `POST /connectors/{source}/sync` — trigger a sync now.

## Scheduler & CSV destination

- APScheduler cron per connector from `config.yaml` (default `0 6 * * *`).
- `exports:` section in config defines named exports (query spec → CSV path);
  exports re-run after each successful sync of a source they reference.
- Manual: `hub sync <source|all>`, `hub export <name|all>`.

## MCP server

FastMCP over stdio (`hub mcp`), registered in the user's Claude config. Tools:
- `list_sources()` — sources, status, freshness
- `list_fields(source)`
- `query_metrics(fields, date_from?, date_to?, date_preset?, filters?)` — same
  semantics as the API; returns compact JSON rows
- `trigger_sync(source)`

Opens DuckDB read-only except `trigger_sync`, which shells out to the CLI to keep
the single-writer rule.

## Error handling

- Auth failures produce actionable messages ("Google token expired — run
  `hub doctor --fix google`").
- `hub doctor` checks each configured connector: credentials load, token valid,
  one-row live probe, DB writable; prints a status table.
- API returns 400 with the invalid field names listed; 503 if DB locked.
- All sync errors are visible via `/connectors` and `hub status`.

## Testing

- Normalizer + storage + API: unit tests with fixture rows (pytest).
- Connectors: parse/normalize tests against recorded JSON fixtures per platform.
- No live API calls in the test suite; live verification is `hub doctor`.

## Milestones

1. Skeleton: models, storage, normalizer, base connector, CLI scaffold + tests
2. Google OAuth helper + GA4 connector end-to-end (sync → DuckDB)
3. GSC + YouTube connectors
4. Query API + presets/aggregation + CSV format
5. Scheduler + CSV exports + `doctor`/`status`
6. MCP server + Claude registration
7. Dormant connectors: Google Ads, Meta Ads (fixture-tested)
