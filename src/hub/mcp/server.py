from __future__ import annotations

import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb
from fastmcp import FastMCP

from hub.connectors.catalog import connector_class, extra_metric_fields
from hub.core.config import HubConfig, load_config
from hub.core.models import CORE_METRICS
from hub.core.presets import COMPARE_MODES, resolve_dates, shift_range
from hub.core.status import source_statuses
from hub.core.storage import STALE_RUNNING as _STALE_RUNNING
from hub.core.storage import Storage

_LOCK_RETRIES = 3
_LOCK_WAIT_S = 0.4


def _with_deltas(current: dict, previous: dict, metric_names: list[str]) -> dict:
    """Merge one row's current + previous metrics into value/prev/change_pct."""
    out = dict(current)
    for m in metric_names:
        cur, prev = current.get(m), previous.get(m)
        out[m] = cur
        out[f"{m}_prev"] = prev
        if cur is not None and prev:
            out[f"{m}_change_pct"] = round((float(cur) - float(prev)) / float(prev) * 100, 1)
        else:
            out[f"{m}_change_pct"] = None
    return out


def build_mcp(config: HubConfig, config_path: str = "config.yaml") -> FastMCP:
    mcp = FastMCP("marketing-data-hub")

    def _cfg() -> HubConfig:
        """Reload config.yaml fresh on every call. The MCP server is a
        long-lived process (Claude Desktop keeps it running for the whole
        session) - a single object captured at startup would silently go
        stale the moment anyone fixes an account mapping or adds a brand
        via 'hub setup'/'hub accounts', causing 403s that look like a
        credentials bug but are really just reading yesterday's settings."""
        return load_config(config_path)

    if not Path(config.db_path).exists():
        Storage(config.db_path).close()  # create schema so read-only open works

    def _open_read_only() -> Storage:
        """A running sync holds the DuckDB write lock, which blocks new read-only
        connections. Retry briefly, then fail with a message the model can act on."""
        last_exc: Exception | None = None
        for attempt in range(_LOCK_RETRIES):
            try:
                return Storage(_cfg().db_path, read_only=True)
            except (duckdb.IOException, duckdb.ConnectionException) as exc:
                last_exc = exc
                if attempt < _LOCK_RETRIES - 1:
                    time.sleep(_LOCK_WAIT_S)
        raise RuntimeError(
            "database is busy - most likely a sync is holding the write lock; "
            f"wait for it to finish (check sync_status) and retry ({last_exc})")

    def _with_storage(fn):
        """Open a short-lived read-only connection so the DB lock is free
        between tool calls (lets trigger_sync's subprocess write)."""
        storage = _open_read_only()
        try:
            return fn(storage)
        finally:
            storage.close()

    def _query_metrics(storage, fields: list[str], date_preset: str | None = None,
                       date_from: str | None = None, date_to: str | None = None,
                       source: str | None = None, campaign: str | None = None,
                       brand: str | None = None, report: str = "core",
                       filters: dict | None = None,
                       compare: str | None = None) -> dict:
        df, dt = resolve_dates(
            date_preset,
            date.fromisoformat(date_from) if date_from else None,
            date.fromisoformat(date_to) if date_to else None)
        filters = dict(filters or {})
        if campaign:
            filters["campaign"] = campaign

        known = storage.accounts()
        matched_names: list[str] = []
        if brand:
            matched_names = sorted({a["account_name"] for a in known
                                    if brand.lower() in a["account_name"].lower()})
            if not matched_names:
                return {"error": f"no brand matching {brand!r}",
                        "available_brands": sorted({a["account_name"] for a in known})}
            # group by account_name so we can filter the aggregated rows per brand
            if "account_name" not in fields:
                fields = [*fields, "account_name"]

        result: dict = {}
        if compare:
            if compare not in COMPARE_MODES:
                return {"error": f"unknown compare mode {compare!r}",
                        "available_modes": list(COMPARE_MODES)}
            if "date" in fields:
                # per-date rows can't be matched across periods; compare totals
                fields = [f for f in fields if f != "date"]
                result["note"] = "date dropped from fields: compare aggregates over the range"

        sources = [source] if source else None
        extra_mets = extra_metric_fields(report, sources)

        def run(a: date, b: date) -> list[dict]:
            rows = storage.query(fields, a, b, sources=sources, filters=filters or None,
                                 report=report, extra_metrics=extra_mets)
            if matched_names:
                rows = [r for r in rows if r.get("account_name") in matched_names]
            return rows

        rows = run(df, dt)
        if compare:
            pf, pt = shift_range(df, dt, compare)
            metric_names = [f for f in fields if f in CORE_METRICS or f in extra_mets]
            dim_names = [f for f in fields if f not in metric_names]
            prev_by_key = {tuple(r.get(d) for d in dim_names): r for r in run(pf, pt)}
            seen = set()
            merged = []
            for r in rows:
                key = tuple(r.get(d) for d in dim_names)
                seen.add(key)
                prev = prev_by_key.get(key, {})
                merged.append(_with_deltas(r, prev, metric_names))
            for key, prev in prev_by_key.items():  # in previous period only
                if key not in seen:
                    gone = {d: prev.get(d) for d in dim_names}
                    merged.append(_with_deltas(gone, prev, metric_names))
            rows = merged
            result["compare"] = compare
            result["compare_date_from"] = pf.isoformat()
            result["compare_date_to"] = pt.isoformat()

        result.update({
            "date_from": df.isoformat(), "date_to": dt.isoformat(),
            "rows": [{k: (v.isoformat() if isinstance(v, date) else v)
                      for k, v in r.items()} for r in rows]})
        if matched_names:
            result["matched_brands"] = matched_names

        # completeness signal: a query over a range with real holes must
        # never look identical to one with none. Checked per-account (not
        # just per-source) - one account's gap can hide behind another
        # account's coverage of the same dates otherwise.
        in_scope = [a for a in known
                    if (a["account_name"] in matched_names if matched_names
                        else (a["source"] == source if source else True))]
        incomplete = []
        for a in in_scope:
            gaps = storage.date_gaps(a["source"], df, dt, report=report,
                                     account_id=a["account_id"])
            if gaps["days_with_data"] < gaps["days_requested"]:
                incomplete.append({"account_name": a["account_name"],
                                   "source": a["source"], **gaps})
        result["days_requested"] = (dt - df).days + 1
        result["complete"] = not incomplete
        if incomplete:
            worst = min(incomplete, key=lambda i: i["days_with_data"])
            result["incomplete_accounts"] = incomplete
            result["warning"] = (
                f"INCOMPLETE DATA: {len(incomplete)} of {len(in_scope)} account(s) "
                f"in this range have missing days (worst: {worst['account_name']} - "
                f"only {worst['days_with_data']}/{worst['days_requested']} days). "
                "Numbers above are a partial sum, not the true total - mention this "
                "when reporting them, or run a backfill to fill the gap first.")
        return result

    def _query_metrics_safe(**kwargs) -> dict:
        try:
            return _with_storage(lambda s: _query_metrics(s, **kwargs))
        except Exception as exc:  # noqa: BLE001 - return readable errors to the model
            return {"error": str(exc)}

    # exposed for tests
    async def _call_query_metrics(**kwargs) -> dict:
        return _query_metrics_safe(**kwargs)
    mcp._call_query_metrics = _call_query_metrics  # type: ignore[attr-defined]

    @mcp.tool()
    def list_sources() -> list[dict]:
        """List marketing data sources (ga4, gsc, ...) with sync status, row counts,
        freshness. For the brands/websites inside each source, use list_brands."""
        return _with_storage(lambda s: source_statuses(config, s))

    @mcp.tool()
    def list_brands() -> list[dict]:
        """List every brand/account in the data (e.g. Vetrotech, Sharekhan,
        L&T Realty) with its source, row count, and date coverage. Call this
        first when the user asks about a specific brand or website."""
        return _with_storage(lambda s: [
            {**a,
             "first_date": a["first_date"].isoformat() if a["first_date"] else None,
             "latest_date": a["latest_date"].isoformat() if a["latest_date"] else None}
            for a in s.accounts()])

    @mcp.tool()
    def list_fields(source: str, report: str = "core") -> list[dict]:
        """List queryable fields for one report of one source. Use list_reports
        first to see which reports exist per source."""
        reports = connector_class(source).get_reports()
        if report not in reports:
            return [{"error": f"unknown report {report!r} for {source!r}",
                     "available_reports": list(reports)}]
        return reports[report].to_dict()

    @mcp.tool()
    def list_reports(source: str | None = None) -> list[dict]:
        """List the available report shapes per source with their dimensions,
        metrics, and what analyses they answer, plus how much data is synced
        for each. Call this before query_metrics when the question needs more
        than daily totals (channels, pages, queries, devices, geo, ...)."""
        coverage = {(c["source"], c["report"]): c
                    for c in _with_storage(lambda s: s.report_coverage())}
        out = []
        for src in (
                [source] if source else list(_cfg().connectors)):
            try:
                reports = connector_class(src).get_reports()
            except (KeyError, ImportError):
                continue
            for name, reg in reports.items():
                cov = coverage.get((src, name))
                out.append({
                    "source": src, "report": name,
                    "description": reg.description,
                    "dimensions": [s.name for s in reg.dimensions()],
                    "metrics": [s.name for s in reg.metrics()],
                    "rows_synced": cov["rows"] if cov else 0,
                    "first_date": cov["first_date"].isoformat() if cov else None,
                    "latest_date": cov["latest_date"].isoformat() if cov else None,
                })
        return out

    @mcp.tool()
    def query_metrics(fields: list[str], date_preset: str | None = None,
                      date_from: str | None = None, date_to: str | None = None,
                      source: str | None = None, campaign: str | None = None,
                      brand: str | None = None, report: str = "core",
                      filters: dict | None = None,
                      compare: str | None = None) -> dict:
        """Query unified marketing metrics, e.g. fields=["date","source","clicks","spend"]
        with date_preset one of last_7d/last_30d/last_90d/this_month/last_month/ytd.

        COMPARISONS: pass compare= to get each metric as value, <metric>_prev and
        <metric>_change_pct against a shifted period. Works with any date range:
        - "prev_period": the equal-length range immediately before (use with a
          calendar month range for MoM, a week range for WoW)
        - "prev_day" / "prev_week": same range shifted 1 day / 7 days (weekday-aligned)
        - "prev_month" / "prev_year": same range shifted one calendar month / year
        The 'date' field is dropped in compare mode (totals over the range).

        FILTERS: filters={"field": "value"} exact-matches any dimension, including
        report extras — e.g. report="events", filters={"event": "form_submit"} for
        one specific event, or report="queries", filters={"device": "MOBILE"}.
        Event names are brand-specific: first query report="events" with
        fields=["event","events"] to discover a brand's event names, then filter.

        PICKING THE RIGHT REPORT (see list_reports for full detail; pass
        source= when using a non-core report):
        - overall trends / totals -> report="core" (default; the only report
          whose GSC numbers are exact totals)
        - traffic mix, organic vs paid -> source="ga4", report="channels"
        - landing-page / entry-page analysis -> source="ga4", report="landing_pages"
        - page behaviour (views, engagement) -> source="ga4", report="pages"
        - device / country segmentation -> source="ga4", report="audience"
          (or source="gsc", report="devices"/"countries" for search data)
        - new vs returning visitors -> source="ga4", report="visitors"
        - specific conversion events (form submits, call clicks, brand-specific
          names) -> source="ga4", report="events" (+ filters={"event": ...})
        - search queries -> source="gsc", report="queries"; branded is
          pre-tagged: fields=["branded","clicks"] or filters={"branded": ...}
        BRANDED/NON-BRANDED FOR CLIENT REPORTS (standard agency methodology):
          branded = sum of branded="true" rows from report="queries";
          non-branded = core-report total MINUS branded. Do NOT report the sum
          of branded="false" rows as non-branded: Google anonymises rare
          queries, so query-level rows only cover ~55-70% of true totals and
          anonymised queries conventionally count as non-branded. Computed this
          way, branded + non-branded = the exact core total. Expect a few %
          difference vs numbers exported from the GSC web UI (UI and API serve
          slightly different datasets).
        - top pages in search -> source="gsc", report="pages"
        Never compare or add numbers across different reports of the same
        source; granularities differ. GSC breakdown reports undercount totals
        slightly (Google anonymises rare queries) — use core for toplines.
        Rates are computed, not stored: engagement rate = engaged_sessions /
        sessions; ctr = clicks / impressions; avg engagement time =
        engagement_seconds / pageviews.

        To answer questions about a specific brand/website (e.g. "Vetrotech traffic
        last week"), pass brand="vetrotech" — it matches account_name
        case-insensitively and partially. Do NOT use the campaign filter for brand
        names; campaigns are ad-campaign names within a brand. If the brand doesn't
        match, the response lists available_brands to pick from.

        CAVEAT: Search Console (gsc) data has a 2-3 day reporting lag from Google,
        so the most recent days of any range will be missing for gsc metrics
        (clicks/impressions) — mention this when reporting recent gsc numbers.
        GA4 data (sessions/users/conversions) is current through yesterday/today.

        COMPLETENESS: every response includes complete=true/false. If false,
        the totals are a PARTIAL SUM over a range with real gaps (not just
        gsc's normal 2-3 day lag) — see incomplete_accounts/warning for which
        account and how many days are missing. Always mention this instead of
        reporting the number as if it were the true total; suggest a backfill."""
        return _query_metrics_safe(
            fields=fields, date_preset=date_preset, date_from=date_from,
            date_to=date_to, source=source, campaign=campaign, brand=brand,
            report=report, filters=filters, compare=compare)

    def _identity_for(cfg: HubConfig, connector: str, target: str) -> str | None:
        """Which Google login owns this property/site (options.identities)."""
        if connector not in cfg.connectors:
            return None
        return (cfg.connectors[connector].options.get("identities") or {}).get(target)

    def _resolve_target(cfg: HubConfig, connector: str, plural_key: str,
                        target: str | None, brand: str | None) -> str | dict:
        """Turn a brand name or explicit id into one configured GA4 property /
        GSC site. Returns the target string, or an error dict."""
        opts = cfg.connectors[connector].options if connector in cfg.connectors else {}
        targets = [str(t) for t in (opts.get(plural_key) or [])]
        labels: dict = opts.get("labels", {})
        if target:
            return str(target)
        if brand:
            hits = [t for t in targets
                    if brand.lower() in str(labels.get(t, t)).lower()]
            if len(hits) == 1:
                return hits[0]
            return {"error": f"brand {brand!r} matched {len(hits)} configured "
                             f"targets: {hits or list(labels.values())}",
                    "hint": "pass the explicit id/url instead"}
        return {"error": "pass either brand= or an explicit target",
                "available": {t: labels.get(t, t) for t in targets}}

    # exposed for tests - proves config.yaml edits made after build_mcp() take
    # effect immediately (the config-reload fix), without needing real
    # Google credentials to exercise query_ga4_live/query_gsc_live directly
    mcp._cfg = _cfg  # type: ignore[attr-defined]
    mcp._identity_for = _identity_for  # type: ignore[attr-defined]
    mcp._resolve_target = _resolve_target  # type: ignore[attr-defined]

    @mcp.tool()
    def query_ga4_live(dimensions: list[str], metrics: list[str],
                       date_from: str, date_to: str,
                       property_id: str | None = None, brand: str | None = None,
                       limit: int = 1000) -> dict:
        """Escape hatch: run any GA4 report live against the API with arbitrary
        native GA4 dimension/metric names (e.g. dimensions=["pagePath","city"],
        metrics=["screenPageViews"]) — for analyses the synced reports don't
        cover. Slower than query_metrics and not stored; prefer query_metrics
        when a synced report answers the question. Pass brand= (e.g. "vetrotech")
        or an explicit property_id. Dates are YYYY-MM-DD."""
        try:
            from google.analytics.data_v1beta import BetaAnalyticsDataClient
            from google.analytics.data_v1beta.types import (
                DateRange, Dimension, Metric, RunReportRequest)

            from hub.connectors.base import AuthError
            from hub.connectors.google_auth import get_credentials, verify_identity_email

            cfg = _cfg()
            target = _resolve_target(cfg, "ga4", "property_ids", property_id, brand)
            if isinstance(target, dict):
                return target
            identity = _identity_for(cfg, "ga4", target)
            ga4_opts = cfg.connectors["ga4"].options if "ga4" in cfg.connectors else {}
            verify_identity_email(cfg.secrets_dir, identity,
                                  ga4_opts.get("identity_emails", {}).get(target),
                                  ga4_opts.get("labels", {}).get(target, target))
            creds = get_credentials(cfg.secrets_dir, identity=identity)
            client = BetaAnalyticsDataClient(credentials=creds)
            response = client.run_report(RunReportRequest(
                property=f"properties/{target}",
                dimensions=[Dimension(name=d) for d in dimensions],
                metrics=[Metric(name=m) for m in metrics],
                date_ranges=[DateRange(start_date=date_from, end_date=date_to)],
                limit=limit))
            rows = [{**{d: r.dimension_values[i].value for i, d in enumerate(dimensions)},
                     **{m: r.metric_values[i].value for i, m in enumerate(metrics)}}
                    for r in response.rows]
            return {"property_id": target, "row_count": len(rows), "rows": rows,
                    "truncated": len(rows) >= limit}
        except AuthError as exc:
            return {"error": str(exc), "hint": exc.hint}
        except Exception as exc:  # noqa: BLE001 - return readable errors to the model
            return {"error": str(exc),
                    "hint": "dimension/metric names must be native GA4 API names; "
                            "see developers.google.com/analytics/devguides/reporting/data/v1/api-schema"}

    @mcp.tool()
    def query_gsc_live(dimensions: list[str], date_from: str, date_to: str,
                       site_url: str | None = None, brand: str | None = None,
                       row_limit: int = 1000) -> dict:
        """Escape hatch: run any Search Console query live with arbitrary
        dimensions from: query, page, date, device, country, searchAppearance
        (e.g. ["query","page"] for query-to-page mapping). Returns clicks,
        impressions, ctr, position per row. Not stored; prefer query_metrics
        when a synced report answers the question. Pass brand= or an explicit
        site_url. Dates are YYYY-MM-DD."""
        try:
            from googleapiclient.discovery import build

            from hub.connectors.base import AuthError
            from hub.connectors.google_auth import get_credentials, verify_identity_email

            cfg = _cfg()
            target = _resolve_target(cfg, "gsc", "site_urls", site_url, brand)
            if isinstance(target, dict):
                return target
            identity = _identity_for(cfg, "gsc", target)
            gsc_opts = cfg.connectors["gsc"].options if "gsc" in cfg.connectors else {}
            verify_identity_email(cfg.secrets_dir, identity,
                                  gsc_opts.get("identity_emails", {}).get(target),
                                  gsc_opts.get("labels", {}).get(target, target))
            creds = get_credentials(cfg.secrets_dir, identity=identity)
            service = build("searchconsole", "v1", credentials=creds,
                            cache_discovery=False)
            resp = service.searchanalytics().query(siteUrl=target, body={
                "startDate": date_from, "endDate": date_to,
                "dimensions": dimensions, "rowLimit": row_limit}).execute()
            rows = [{**dict(zip(dimensions, r["keys"])),
                     "clicks": r.get("clicks"), "impressions": r.get("impressions"),
                     "ctr": r.get("ctr"), "position": r.get("position")}
                    for r in resp.get("rows", [])]
            return {"site_url": target, "row_count": len(rows), "rows": rows,
                    "truncated": len(rows) >= row_limit}
        except AuthError as exc:
            return {"error": str(exc), "hint": exc.hint}
        except Exception as exc:  # noqa: BLE001 - return readable errors to the model
            return {"error": str(exc)}

    @mcp.tool()
    def list_identities() -> dict:
        """List the Google logins (identities) that have saved tokens. The hub
        supports multiple Google accounts: 'default' is the original login;
        more are added by running 'hub login <name>' in a terminal (it opens a
        browser to sign in - it cannot be done from here). Pass an identity to
        list_available_accounts to browse what that login can see."""
        try:
            from hub.connectors.google_auth import list_identities as _idents

            return {"identities": _idents(_cfg().secrets_dir),
                    "add_more": "run in a terminal: hub login <name>"}
        except Exception as exc:  # noqa: BLE001 - return readable errors to the model
            return {"error": str(exc)}

    @mcp.tool()
    def list_available_accounts(source: str | None = None,
                                identity: str = "default") -> list[dict] | dict:
        """Windsor-style onboarding: list every GA4 property and Search Console
        site one Google login can access (source: "ga4" | "gsc" | omit for
        both), with configured=true on those already syncing. With multiple
        logins, pass identity= (see list_identities). Show the user the
        unconfigured ones and ask which to add, then call add_accounts."""
        try:
            from hub.connectors.google_auth import get_credentials
            from hub.core.accounts import annotate_configured, discover_all

            cfg = _cfg()
            creds = get_credentials(cfg.secrets_dir, identity=identity)
            return annotate_configured(discover_all(creds, source), cfg)
        except Exception as exc:  # noqa: BLE001 - return readable errors to the model
            return {"error": str(exc)}

    @mcp.tool()
    def add_accounts(source: str, account_ids: list[str],
                     identity: str = "default") -> dict:
        """Add accounts the user selected to config.yaml (source: "ga4" or
        "gsc"; account_ids from list_available_accounts). Labels are filled
        from the account names automatically; pass the same identity= you used
        for list_available_accounts so syncs use the right Google login. Only
        ids visible to that login are accepted. ALWAYS confirm the specific
        accounts with the user before calling this. After adding: trigger_sync
        for a first load, and suggest a backfill for history."""
        try:
            from hub.connectors.google_auth import get_credentials
            from hub.core.accounts import add_accounts as _add
            from hub.core.accounts import discover_all

            secrets_dir = _cfg().secrets_dir
            creds = get_credentials(secrets_dir, identity=identity)
            visible = {a["id"]: a for a in discover_all(creds, source)}
            unknown = [i for i in account_ids if i not in visible]
            if unknown:
                return {"error": f"not visible to this Google login: {unknown}",
                        "hint": "use ids exactly as returned by list_available_accounts"}
            added = _add(config_path, source,
                         [visible[i] for i in account_ids], identity=identity,
                         secrets_dir=secrets_dir)
            # no in-memory patching needed - every tool call reloads config.yaml
            # fresh (_cfg()), so the file write above is immediately visible
            return {"added": added,
                    "skipped_already_configured":
                        [i for i in account_ids if i not in added],
                    "next_steps": "trigger_sync to load the rolling window; run "
                                  "'hub backfill' from a terminal for history"}
        except Exception as exc:  # noqa: BLE001 - return readable errors to the model
            return {"error": str(exc)}

    sync_log_path = Path(config_path).resolve().parent / "logs" / "mcp_sync.log"
    # a just-spawned sync takes ~1s to write its 'running' row, so the DB check
    # alone can't stop an immediate double-trigger — track our own child too
    last_spawned: dict = {"proc": None, "source": None}

    def _running_source(storage) -> str | None:
        for src, run in storage.last_runs().items():
            if (run["status"] == "running" and run["started_at"]
                    and datetime.now() - run["started_at"] < _STALE_RUNNING):
                return src
        return None

    def _trigger_sync(source: str) -> dict:
        proc = last_spawned["proc"]
        if proc is not None and proc.poll() is None:
            return {"status": "already_running",
                    "detail": f"a sync of {last_spawned['source']!r} started from "
                              "this session is still running - poll sync_status "
                              "until it finishes"}
        try:
            running = _with_storage(_running_source)
        except RuntimeError as exc:
            # can't even read the DB -> a sync already holds the write lock
            return {"status": "already_running", "detail": str(exc)}
        if running:
            return {"status": "already_running",
                    "detail": f"a sync of {running!r} is still running - "
                              "poll sync_status until it finishes"}
        sync_log_path.parent.mkdir(parents=True, exist_ok=True)
        with sync_log_path.open("a", encoding="utf-8") as log:
            log.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] "
                      f"MCP triggered sync {source!r}\n")
            log.flush()
            last_spawned["proc"] = subprocess.Popen(
                [sys.executable, "-m", "hub.cli", "sync", source,
                 "--config", config_path],
                stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                creationflags=(subprocess.CREATE_NO_WINDOW
                               if sys.platform == "win32" else 0))
            last_spawned["source"] = source

        # a bare "success" reads as "you're caught up" - it isn't. This is
        # only ever a ROLLING window; a gap from weeks/months ago (an auth
        # outage, a broken property) is never touched by this call, no
        # matter how many times it's run. Say the actual window up front.
        cfg = _cfg()
        expanded = list(cfg.connectors) if source == "all" else [source]
        windows = {s: cfg.connectors[s].window_days for s in expanded
                  if s in cfg.connectors}
        today = date.today()
        window_desc = ", ".join(
            f"{s}: last {d} days ({(today - timedelta(days=d)).isoformat()} to "
            f"{today.isoformat()})" for s, d in windows.items())
        return {"status": "started", "source": source, "log": str(sync_log_path),
                "sync_window": window_desc or None,
                "note": f"This ONLY refreshes a rolling window ({window_desc}) - "
                        "it does NOT fill in older gaps, no matter what the result "
                        "says. If history further back is missing (check "
                        "query_metrics' complete=false / days_with_data), that "
                        "needs a separate backfill, not another trigger_sync. "
                        "Runs in the background - poll sync_status to see when it "
                        "finishes; queries may briefly report the database as busy "
                        "while the sync holds the write lock."}

    def _sync_status(storage) -> dict:
        runs = {}
        for src, run in storage.last_runs().items():
            runs[src] = {
                "status": run["status"],
                "started_at": run["started_at"].isoformat() if run["started_at"] else None,
                "finished_at": run["finished_at"].isoformat() if run["finished_at"] else None,
                "rows_written": run["rows_written"],
                "error_message": run["error_message"],
                # the actual window this run covered - "success" over the
                # last 30 days is not the same as "success, fully caught up"
                "date_from": run["date_from"].isoformat() if run["date_from"] else None,
                "date_to": run["date_to"].isoformat() if run["date_to"] else None,
            }
        return {"runs": runs,
                "sync_in_progress": _running_source(storage) is not None}

    def _sync_status_safe() -> dict:
        try:
            return _with_storage(_sync_status)
        except Exception as exc:  # noqa: BLE001 - return readable errors to the model
            return {"error": str(exc), "sync_in_progress": True}

    # exposed for tests
    async def _call_trigger_sync(**kwargs) -> dict:
        return _trigger_sync(**kwargs)
    mcp._call_trigger_sync = _call_trigger_sync  # type: ignore[attr-defined]

    async def _call_sync_status() -> dict:
        return _sync_status_safe()
    mcp._call_sync_status = _call_sync_status  # type: ignore[attr-defined]

    @mcp.tool()
    def trigger_sync(source: str) -> dict:
        """Start a sync for one source (or 'all') in the background and return
        immediately. A full sync takes a few minutes - poll sync_status to see
        when it finishes, then query. Refuses to start if a sync is already
        running.

        IMPORTANT: this ONLY refreshes a rolling window (see sync_window in
        the response, e.g. 'last 30 days') - it does NOT fill in older gaps.
        A 'success' status means that recent window synced cleanly, NOT that
        all history is now present. If older data is missing, that needs an
        actual backfill (a separate operation, run from a terminal:
        'hub backfill <source> --from YYYY-MM-DD'), not another trigger_sync."""
        return _trigger_sync(source)

    @mcp.tool()
    def sync_status() -> dict:
        """Show each source's most recent sync run: status, timestamps, rows,
        and the exact date_from/date_to it covered - a run's date range can
        be much narrower than the account's full history (see trigger_sync),
        so check this before assuming 'success' means fully caught up. Call
        after trigger_sync to know when fresh data is queryable."""
        return _sync_status_safe()

    return mcp
