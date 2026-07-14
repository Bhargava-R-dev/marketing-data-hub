from __future__ import annotations

import csv
import io
import os
from datetime import date

import duckdb
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import Response

from hub.connectors.catalog import (ALL_CONNECTORS, build_connector, connector_class,
                                    extra_metric_fields)
from hub.core.config import HubConfig
from hub.core.models import CORE_DIMENSIONS, CORE_METRICS
from hub.core.presets import resolve_dates
from hub.core.status import source_statuses
from hub.core.storage import Storage
from hub.core.sync import run_sync


def _check_api_key(request: Request) -> None:
    expected = os.environ.get("HUB_API_KEY", "")
    if not expected:
        raise HTTPException(status_code=500,
                            detail="HUB_API_KEY is not set on the server - add it to .env")
    # plain != is fine here: localhost-bound single-user tool, timing attacks not in scope
    supplied = request.headers.get("X-API-Key") or request.query_params.get("api_key")
    if supplied != expected:
        raise HTTPException(status_code=401, detail="invalid or missing API key")


def _known_fields(config: HubConfig, source: str) -> set[str]:
    known = set(CORE_DIMENSIONS) | set(CORE_METRICS)
    sources = ALL_CONNECTORS if source == "all" else [source]
    for s in sources:
        try:
            for registry in connector_class(s).get_reports().values():
                known |= set(registry.names())
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
    def list_fields(source: str, report: str = "core") -> list[dict]:
        if source not in ALL_CONNECTORS:
            raise HTTPException(status_code=404, detail=f"unknown source {source!r}")
        reports = connector_class(source).get_reports()
        if report not in reports:
            raise HTTPException(status_code=404,
                                detail=f"unknown report {report!r} for {source!r} "
                                       f"(available: {list(reports)})")
        return reports[report].to_dict()

    @app.get("/connectors/{source}/reports")
    def list_reports(source: str) -> list[dict]:
        if source not in ALL_CONNECTORS:
            raise HTTPException(status_code=404, detail=f"unknown source {source!r}")
        return [{"report": name, "description": reg.description,
                 "dimensions": [s.name for s in reg.dimensions()],
                 "metrics": [s.name for s in reg.metrics()]}
                for name, reg in connector_class(source).get_reports().items()]

    @app.get("/connectors/{source}/data")
    def get_data(source: str,
                 fields: str = Query(...),
                 date_from: date | None = None,
                 date_to: date | None = None,
                 date_preset: str | None = None,
                 campaign: str | None = None,
                 account_id: str | None = None,
                 report: str = "core",
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
            rows = storage.query(field_list, df, dt, sources=sources, filters=filters,
                                 report=report,
                                 extra_metrics=extra_metric_fields(report, sources))
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
