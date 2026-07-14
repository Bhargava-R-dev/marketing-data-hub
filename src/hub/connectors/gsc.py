from __future__ import annotations

from datetime import date
from typing import Iterable

from hub.connectors.base import BaseConnector, FieldRegistry, FieldSpec, resolve_targets
from hub.connectors.google_auth import get_credentials

_ROW_LIMIT = 25_000  # Search Console API max rows per request


def _gsc_registry(extra_dim: FieldSpec | None, description: str) -> FieldRegistry:
    specs = [FieldSpec("date", "date", dimension=True)]
    if extra_dim:
        specs.append(extra_dim)
    specs += [
        FieldSpec("clicks", "clicks"),
        FieldSpec("impressions", "impressions"),
        FieldSpec("ctr", "ctr", additive=False,
                  description="click-through rate (recompute as clicks/impressions "
                              "when aggregating)"),
        FieldSpec("position", "position", additive=False,
                  description="avg SERP position (not additive - don't sum)"),
    ]
    return FieldRegistry(specs, description=description)


GSC_FIELDS = _gsc_registry(
    None, "accurate daily site totals (breakdown reports undercount slightly "
          "because Google anonymises rare queries)")

GSC_REPORTS: dict[str, FieldRegistry] = {
    "queries": _gsc_registry(
        FieldSpec("query", "query", dimension=True),
        "search-query performance; branded vs non-branded = string-match on query"),
    "pages": _gsc_registry(
        FieldSpec("page", "page", dimension=True),
        "per-URL search performance (top pages, page-level position trends)"),
    "devices": _gsc_registry(
        FieldSpec("device", "device", dimension=True),
        "MOBILE / DESKTOP / TABLET split"),
    "countries": _gsc_registry(
        FieldSpec("country", "country", dimension=True),
        "per-country search performance (ISO 3166-1 alpha-3 codes)"),
}


def parse_gsc_response(resp: dict, site_url: str, account_name: str | None = None,
                       dims: tuple[str, ...] = ("date",)) -> list[dict]:
    out = []
    for row in resp.get("rows", []):
        raw = {
            "account_id": site_url, "account_name": account_name or site_url,
            "clicks": row.get("clicks"), "impressions": row.get("impressions"),
            "ctr": row.get("ctr"), "position": row.get("position"),
        }
        for dim, key in zip(dims, row["keys"]):
            raw[dim] = key
        out.append(raw)
    return out


class SearchConsoleConnector(BaseConnector):
    id = "gsc"
    fields = GSC_FIELDS
    reports = GSC_REPORTS

    def authenticate(self) -> None:
        self._creds = get_credentials(self.secrets_dir)

    def extract(self, date_from: date, date_to: date) -> Iterable[dict]:
        return self.extract_report("core", date_from, date_to)

    def extract_report(self, report: str, date_from: date,
                       date_to: date) -> Iterable[dict]:
        from googleapiclient.discovery import build

        registry = self.get_reports()[report]
        # unified name == native name for every GSC dimension
        dims = tuple(s.name for s in registry.dimensions())
        site_urls = resolve_targets(self.settings.options, "site_urls", "site_url")
        labels = self.settings.options.get("labels", {})
        service = build("searchconsole", "v1", credentials=self._creds,
                        cache_discovery=False)
        results: list[dict] = []
        for site_url in site_urls:
            start_row = 0
            while True:
                body = {"startDate": date_from.isoformat(),
                        "endDate": date_to.isoformat(),
                        "dimensions": list(dims),
                        "rowLimit": _ROW_LIMIT, "startRow": start_row}
                resp = service.searchanalytics().query(
                    siteUrl=site_url, body=body).execute()
                page = resp.get("rows", [])
                results.extend(parse_gsc_response(
                    resp, site_url, labels.get(site_url), dims))
                if len(page) < _ROW_LIMIT:
                    break
                start_row += _ROW_LIMIT
        return results
