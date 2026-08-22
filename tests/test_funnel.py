"""query_ga4_funnel: general-purpose multi-step funnel analysis for any
configured GA4 property, via GA4's dedicated Funnel Exploration API (v1alpha)
- a different endpoint from query_ga4_live because funnel steps can only be
expressed as events/event-parameters, not arbitrary dimensions like pagePath."""
import asyncio

import pytest

from hub.core.config import ConnectorSettings, HubConfig
from hub.mcp.server import build_mcp


def make_config(tmp_path, **ga4_options):
    # _cfg() (server.py) reloads config.yaml fresh on every tool call, so the
    # in-memory HubConfig below is only the initial build_mcp() argument -
    # what actually governs _call_query_ga4_funnel is this YAML file.
    db_path = (tmp_path / "t.duckdb").as_posix()
    options = {"property_ids": ["123456789"], "labels": {"123456789": "Vetrotech"},
              **ga4_options}
    (tmp_path / "config.yaml").write_text(
        f"db_path: {db_path}\nconnectors:\n  ga4:\n    options:\n"
        f"      property_ids: [\"123456789\"]\n"
        f"      labels: {{\"123456789\": Vetrotech}}\n",
        encoding="utf-8")
    return HubConfig(db_path=db_path,
                     connectors={"ga4": ConnectorSettings(options=options)})


def test_funnel_tool_registered(tmp_path):
    cfg = make_config(tmp_path)
    mcp = build_mcp(cfg, config_path=str(tmp_path / "config.yaml"))
    tools = asyncio.run(mcp.list_tools())
    assert "query_ga4_funnel" in {t.name for t in tools}


def test_funnel_requires_at_least_two_steps(tmp_path):
    cfg = make_config(tmp_path)
    mcp = build_mcp(cfg, config_path=str(tmp_path / "config.yaml"))
    result = asyncio.run(mcp._call_query_ga4_funnel(
        steps=[{"name": "Landed", "event": "page_view"}],
        date_from="2026-07-01", date_to="2026-07-31"))
    assert "error" in result and "at least 2" in result["error"]


def test_funnel_rejects_too_many_steps(tmp_path):
    cfg = make_config(tmp_path)
    mcp = build_mcp(cfg, config_path=str(tmp_path / "config.yaml"))
    steps = [{"name": f"step {i}", "event": "page_view"} for i in range(11)]
    result = asyncio.run(mcp._call_query_ga4_funnel(
        steps=steps, date_from="2026-07-01", date_to="2026-07-31"))
    assert "error" in result and "10 steps" in result["error"]


def test_funnel_requires_name_and_event_per_step(tmp_path):
    cfg = make_config(tmp_path)
    mcp = build_mcp(cfg, config_path=str(tmp_path / "config.yaml"))
    result = asyncio.run(mcp._call_query_ga4_funnel(
        steps=[{"name": "Landed"}, {"name": "Converted", "event": "purchase"}],
        date_from="2026-07-01", date_to="2026-07-31"))
    assert "error" in result and "'name' and 'event'" in result["error"]


def test_funnel_unknown_brand_returns_available_targets(tmp_path):
    cfg = make_config(tmp_path)
    mcp = build_mcp(cfg, config_path=str(tmp_path / "config.yaml"))
    result = asyncio.run(mcp._call_query_ga4_funnel(
        steps=[{"name": "Landed", "event": "page_view"},
              {"name": "Converted", "event": "purchase"}],
        date_from="2026-07-01", date_to="2026-07-31", brand="nike"))
    assert "error" in result
    assert result["error"].count("matched 0 configured targets")


def test_funnel_no_target_given_lists_available(tmp_path):
    cfg = make_config(tmp_path)
    mcp = build_mcp(cfg, config_path=str(tmp_path / "config.yaml"))
    result = asyncio.run(mcp._call_query_ga4_funnel(
        steps=[{"name": "Landed", "event": "page_view"},
              {"name": "Converted", "event": "purchase"}],
        date_from="2026-07-01", date_to="2026-07-31"))
    assert "error" in result
    assert result["available"] == {"123456789": "Vetrotech"}


def test_funnel_happy_path_parses_response(tmp_path, monkeypatch):
    from google.analytics.data_v1alpha.types import (
        DimensionHeader, DimensionValue, FunnelSubReport, MetricHeader,
        MetricValue, Row, RunFunnelReportResponse)

    cfg = make_config(tmp_path)

    headers = [MetricHeader(name=n) for n in
              ["activeUsers", "funnelStepCompletionRate", "funnelStepAbandonments",
               "funnelStepAbandonmentRate"]] * 2
    row0 = Row(
        dimension_values=[DimensionValue(value="1. Landed on page")],
        metric_values=[MetricValue(value="22606"), MetricValue(value="0.0136"),
                       MetricValue(value="22299"), MetricValue(value="0.9864")])
    row1 = Row(
        dimension_values=[DimensionValue(value="2. Generated lead")],
        metric_values=[MetricValue(value="307"), MetricValue(value="1.0"),
                       MetricValue(value="0"), MetricValue(value="0.0")])
    fake_response = RunFunnelReportResponse(
        funnel_table=FunnelSubReport(
            dimension_headers=[DimensionHeader(name="funnelStepName")],
            metric_headers=headers, rows=[row0, row1]))

    class FakeClient:
        def __init__(self, credentials=None):
            pass

        def run_funnel_report(self, request):
            return fake_response

    monkeypatch.setattr("google.analytics.data_v1alpha.AlphaAnalyticsDataClient",
                        FakeClient)
    monkeypatch.setattr("hub.connectors.google_auth.get_credentials",
                        lambda *a, **k: object())

    mcp = build_mcp(cfg, config_path=str(tmp_path / "config.yaml"))
    result = asyncio.run(mcp._call_query_ga4_funnel(
        steps=[{"name": "Landed on page", "event": "page_view", "page": "/"},
              {"name": "Generated lead", "event": "generate_lead"}],
        date_from="2026-07-01", date_to="2026-07-31", property_id="123456789"))

    assert result["property_id"] == "123456789"
    assert len(result["steps"]) == 2
    step1, step2 = result["steps"]
    assert step1["active_users"] == 22606
    assert step1["completion_rate"] == pytest.approx(0.0136)
    assert step1["abandonments"] == 22299
    assert step2["active_users"] == 307
    assert step2["completion_rate"] == 1.0
