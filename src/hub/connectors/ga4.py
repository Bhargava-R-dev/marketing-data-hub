from __future__ import annotations

from datetime import date
from typing import Iterable

from hub.connectors.base import (BaseConnector, FieldRegistry, FieldSpec,
                                 group_by_identity, resolve_targets)
from hub.connectors.google_auth import get_credentials

_PAGE_SIZE = 250_000  # GA4 Data API max rows per request

GA4_FIELDS = FieldRegistry([
    FieldSpec("date", "date", dimension=True),
    FieldSpec("campaign", "sessionCampaignName", dimension=True),
    FieldSpec("sessions", "sessions"),
    FieldSpec("users", "totalUsers"),
    FieldSpec("conversions", "keyEvents"),
    FieldSpec("conversion_value", "purchaseRevenue"),
], description="daily campaign-level traffic and conversion totals")

# Only additive metrics are stored (counts, not rates): rates like bounce rate
# or engagement rate must be computed downstream from engaged_sessions/sessions,
# otherwise aggregation over days/dimensions would be wrong.
GA4_REPORTS: dict[str, FieldRegistry] = {
    "channels": FieldRegistry([
        FieldSpec("date", "date", dimension=True),
        FieldSpec("channel", "sessionDefaultChannelGroup", dimension=True,
                  description="default channel group, e.g. Organic Search / Paid Search / Direct"),
        FieldSpec("sessions", "sessions"),
        FieldSpec("users", "totalUsers"),
        FieldSpec("conversions", "keyEvents"),
        FieldSpec("engaged_sessions", "engagedSessions",
                  description="engagement rate = engaged_sessions / sessions"),
        FieldSpec("pageviews", "screenPageViews"),
    ], description="traffic mix by acquisition channel (organic vs paid vs direct...)"),
    "landing_pages": FieldRegistry([
        FieldSpec("date", "date", dimension=True),
        FieldSpec("landing_page", "landingPagePlusQueryString", dimension=True),
        FieldSpec("channel", "sessionDefaultChannelGroup", dimension=True),
        FieldSpec("sessions", "sessions"),
        FieldSpec("users", "totalUsers"),
        FieldSpec("conversions", "keyEvents"),
        FieldSpec("engaged_sessions", "engagedSessions"),
    ], description="entry-page performance per channel (top organic landing pages, "
                   "landing/blog/commercial page splits)"),
    "pages": FieldRegistry([
        FieldSpec("date", "date", dimension=True),
        FieldSpec("page", "pagePath", dimension=True),
        FieldSpec("pageviews", "screenPageViews"),
        FieldSpec("users", "totalUsers"),
        FieldSpec("engagement_seconds", "userEngagementDuration",
                  description="avg engagement time = engagement_seconds / pageviews"),
        FieldSpec("events", "eventCount"),
    ], description="page behaviour: views, engagement time, events per page path"),
    "audience": FieldRegistry([
        FieldSpec("date", "date", dimension=True),
        FieldSpec("device", "deviceCategory", dimension=True),
        FieldSpec("country", "country", dimension=True),
        FieldSpec("sessions", "sessions"),
        FieldSpec("users", "totalUsers"),
        FieldSpec("conversions", "keyEvents"),
        FieldSpec("engaged_sessions", "engagedSessions"),
    ], description="segmentation by device category and country"),
    "visitors": FieldRegistry([
        FieldSpec("date", "date", dimension=True),
        FieldSpec("visitor_type", "newVsReturning", dimension=True,
                  description="'new' or 'returning' (cohort-lite; true user-level "
                              "cohorts need the GA4 BigQuery export)"),
        FieldSpec("sessions", "sessions"),
        FieldSpec("users", "totalUsers"),
        FieldSpec("conversions", "keyEvents"),
    ], description="new vs returning visitor split for retention trends"),
    "events": FieldRegistry([
        FieldSpec("date", "date", dimension=True),
        FieldSpec("event", "eventName", dimension=True,
                  description="event name, brand-specific (form_submit, call_click, "
                              "generate_lead, ...) - filter with filters={'event': ...}"),
        FieldSpec("events", "eventCount"),
        FieldSpec("conversions", "keyEvents",
                  description="non-zero only for events marked as key events"),
        FieldSpec("users", "totalUsers"),
    ], description="per-event counts by event name; answers 'how many form submits / "
                   "call clicks' for any brand's own event taxonomy"),
}

_N2U = GA4_FIELDS.native_to_unified()


def parse_ga4_report(report: dict, property_id: str, account_name: str | None = None,
                     n2u: dict[str, str] | None = None) -> list[dict]:
    n2u = n2u or _N2U
    dims = [h["name"] for h in report.get("dimensionHeaders", [])]
    mets = [h["name"] for h in report.get("metricHeaders", [])]
    out = []
    for row in report.get("rows", []):
        values = [v["value"] for v in row["dimensionValues"]]
        # GA4 buckets unattributable/overflow rows into a spurious '(other)' row
        # whose metrics do NOT reconcile with the real total (it inflated big
        # properties' breakdowns by 30-40%). Drop it: breakdown reports then sum
        # to slightly UNDER the topline (like GSC query anonymisation) - use the
        # 'core' report for exact totals.
        if "(other)" in values:
            continue
        raw: dict = {"account_id": property_id,
                     "account_name": account_name or f"GA4 {property_id}"}
        for name, value in zip(dims, values):
            raw[n2u[name]] = value
        for name, v in zip(mets, row["metricValues"]):
            raw[n2u[name]] = v["value"]
        d = raw["date"]  # GA4 returns YYYYMMDD
        raw["date"] = f"{d[:4]}-{d[4:6]}-{d[6:]}"
        out.append(raw)
    return out


class GA4Connector(BaseConnector):
    id = "ga4"
    fields = GA4_FIELDS
    reports = GA4_REPORTS

    def authenticate(self) -> None:
        # one credential per Google login: properties may live under different
        # gmail/google accounts, mapped via options.identities
        property_ids = resolve_targets(self.settings.options, "property_ids", "property_id")
        groups = group_by_identity(property_ids, self.settings.options)
        self._creds = {ident: get_credentials(self.secrets_dir, identity=ident)
                       for ident in groups}
        self._groups = groups

    def extract(self, date_from: date, date_to: date) -> Iterable[dict]:
        return self.extract_report("core", date_from, date_to)

    def extract_report(self, report: str, date_from: date,
                       date_to: date) -> Iterable[dict]:
        from google.analytics.data_v1beta import BetaAnalyticsDataClient

        registry = self.get_reports()[report]
        n2u = registry.native_to_unified()
        labels = self.settings.options.get("labels", {})
        results: list[dict] = []
        for identity, property_ids in self._groups.items():
            client = BetaAnalyticsDataClient(credentials=self._creds[identity])
            for property_id in property_ids:
                results.extend(self._fetch(
                    client, registry, n2u, property_id, labels.get(property_id),
                    date_from, date_to))
        return results

    def _fetch(self, client, registry: FieldRegistry, n2u: dict,
               property_id: str, label: str | None,
               date_from: date, date_to: date) -> list[dict]:
        """Fetch one property/range, paging past the row cap. '(other)' rows
        are dropped in parse_ga4_report (they don't reconcile with totals)."""
        from google.analytics.data_v1beta.types import (
            DateRange, Dimension, Metric, RunReportRequest, RunReportResponse)

        results: list[dict] = []
        offset = 0
        while True:
            request = RunReportRequest(
                property=f"properties/{property_id}",
                dimensions=[Dimension(name=s.native) for s in registry.dimensions()],
                metrics=[Metric(name=s.native) for s in registry.metrics()],
                date_ranges=[DateRange(start_date=date_from.isoformat(),
                                       end_date=date_to.isoformat())],
                limit=_PAGE_SIZE,
                offset=offset,
            )
            response = client.run_report(request)
            rep = RunReportResponse.to_dict(response, preserving_proto_field_name=False)
            results.extend(parse_ga4_report(rep, property_id, label, n2u))
            if len(rep.get("rows", [])) < _PAGE_SIZE:
                break
            offset += _PAGE_SIZE
        return results
