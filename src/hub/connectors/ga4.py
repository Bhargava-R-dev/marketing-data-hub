from __future__ import annotations

from datetime import date
from typing import Iterable

from hub.connectors.base import BaseConnector, FieldRegistry, FieldSpec, resolve_targets
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


def parse_ga4_report(report: dict, property_id: str, account_name: str | None = None) -> list[dict]:
    dims = [h["name"] for h in report.get("dimensionHeaders", [])]
    mets = [h["name"] for h in report.get("metricHeaders", [])]
    out = []
    for row in report.get("rows", []):
        raw: dict = {"account_id": property_id,
                     "account_name": account_name or f"GA4 {property_id}"}
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

        property_ids = resolve_targets(self.settings.options, "property_ids", "property_id")
        labels = self.settings.options.get("labels", {})
        client = BetaAnalyticsDataClient(credentials=self._creds)
        results: list[dict] = []
        for property_id in property_ids:
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
            results.extend(parse_ga4_report(report, property_id, labels.get(property_id)))
        return results
