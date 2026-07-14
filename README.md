# Marketing Data Hub

Personal Windsor.ai-style pipeline: pulls GA4, Search Console, YouTube (and, once
activated, Google Ads + Meta Ads) into a unified DuckDB schema, queryable via a
Windsor-style REST API, scheduled CSV exports, and an MCP server for Claude.

## Reports (analysis shapes)

Each source syncs several named *reports* — different dimensional shapes of the
same data, stored side by side and never mixed (mixing granularities would
double-count):

| Source | Report | Answers |
|---|---|---|
| ga4 | `core` | daily campaign totals (sessions, users, conversions, revenue) |
| ga4 | `channels` | traffic mix: organic vs paid vs direct, engagement, pageviews |
| ga4 | `landing_pages` | entry-page performance per channel |
| ga4 | `pages` | page behaviour: views, engagement time, events per path |
| ga4 | `audience` | device × country segmentation |
| ga4 | `visitors` | new vs returning (cohort-lite) |
| gsc | `core` | exact daily search totals per site |
| gsc | `queries` | per-query performance (branded split = string-match) |
| gsc | `pages` | per-URL search performance |
| gsc | `devices` / `countries` | mobile/desktop and geo splits |
| ga4 | `events` | per-event counts by name (brand-specific: form_submit, call_click...) |

Pass `report=<name>` to the API/MCP `query_metrics`; default is `core`.
MCP `query_metrics` also supports `compare=` (prev_period / prev_day / prev_week /
prev_month / prev_year — returns value, previous, and %-change per metric for any
date range) and `filters=` (exact match on any dimension incl. report extras,
e.g. `{"event": "form_submit"}` or `{"device": "MOBILE"}`).
Rates are computed, not stored: engagement rate = engaged_sessions/sessions,
ctr = clicks/impressions, avg engagement time = engagement_seconds/pageviews.
GSC breakdown reports undercount totals slightly (Google anonymises rare
queries) — use `core` for toplines. True user-level cohorts need the GA4
BigQuery export; `visitors` + the live tools cover cohort-lite analysis.

For anything the synced reports don't cover, the MCP tools `query_ga4_live`
and `query_gsc_live` pass arbitrary dimension/metric combinations straight to
the APIs on demand.

## Setup

1. `python -m pip install -e ".[dev]"`
2. Copy `config.yaml.example` → `config.yaml`; fill in your GA4 `property_id`
   and Search Console `site_url`. Have multiple GA4 properties or Search Console
   sites under the same Google login? Use `property_ids: [...]` / `site_urls: [...]`
   instead — all of them sync, and every row is tagged with its own `account_id`
   so they stay distinguishable downstream.
3. Copy `.env.example` → `.env`; set a random `HUB_API_KEY`.
4. Google Cloud Console → create a project → enable **Google Analytics Data API**,
   **Search Console API**, **YouTube Analytics API** → create an **OAuth client
   (Desktop app)** → download JSON to `secrets/google_client.json`.
5. `hub doctor` — first run opens a browser to authorize; then all checks go green.

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
`format=csv` for CSV, `report=<name>` for a breakdown report. `/connectors`
lists sources; `/connectors/{source}/reports` lists report shapes;
`/connectors/{source}/fields?report=<name>` lists fields.

## Claude MCP

`claude mcp add marketing-hub -- python -m hub.cli mcp --config <absolute-path>/config.yaml`
Then ask Claude: "How did my campaigns do last week?"

Note: use an absolute path for --config; the MCP process may be launched from a
different working directory.

`trigger_sync` starts the sync in the background and returns immediately
(output goes to `logs/mcp_sync.log`); poll `sync_status` to see when it
finishes. While a sync holds the write lock, query tools return a readable
"database is busy" error instead of hanging.

## Activating the ad connectors

- **Google Ads:** apply for a developer token (API Center), then uncomment
  `google_ads` in config.yaml and fill options.
- **Meta Ads:** create a Meta app, generate a long-lived token with `ads_read`,
  uncomment `meta_ads` and fill options.

## Known limitations

- DuckDB allows one writer: run `hub mcp` OR `hub serve`, not both at once
  (trigger_sync from MCP spawns the CLI, which needs the write lock free).
  While any sync runs, MCP query tools report "database is busy" until it
  finishes (~3 min for `sync all`).
- Extras fields (e.g. position, ctr, views) are returned as strings by the query
  API — cast numerically as needed.
