# Marketing Data Hub

Personal Windsor.ai-style pipeline: pulls GA4, Search Console, YouTube (and, once
activated, Google Ads + Meta Ads) into a unified DuckDB schema, queryable via a
Windsor-style REST API, scheduled CSV exports, and an MCP server for Claude.

## Setup

1. `python -m pip install -e ".[dev]"`
2. Copy `config.yaml.example` → `config.yaml`; fill in your GA4 `property_id`
   and Search Console `site_url`.
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
`format=csv` for CSV. `/connectors` lists sources; `/connectors/{source}/fields`
lists fields.

## Claude MCP

`claude mcp add marketing-hub -- python -m hub.cli mcp --config <absolute-path>/config.yaml`
Then ask Claude: "How did my campaigns do last week?"

Note: use an absolute path for --config; the MCP process may be launched from a
different working directory.

## Activating the ad connectors

- **Google Ads:** apply for a developer token (API Center), then uncomment
  `google_ads` in config.yaml and fill options.
- **Meta Ads:** create a Meta app, generate a long-lived token with `ads_read`,
  uncomment `meta_ads` and fill options.

## Known limitations

- DuckDB allows one writer: run `hub mcp` OR `hub serve`, not both at once
  (trigger_sync from MCP shells out to the CLI, which needs the write lock free).
- Extras fields (e.g. position, ctr, views) are returned as strings by the query
  API — cast numerically as needed.
