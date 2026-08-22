from __future__ import annotations

from datetime import date
from typing import Iterable

from hub.connectors.base import (BaseConnector, FieldRegistry, FieldSpec,
                                 group_by_identity, resolve_targets)
from hub.connectors.google_auth import get_credentials, verify_identity_email

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
    "queries": FieldRegistry([
        *_gsc_registry(
            FieldSpec("query", "query", dimension=True), "").specs,
        # computed at sync time from options.brand_terms, not an API field
        FieldSpec("branded", "_computed", dimension=True,
                  description="'true'/'false' if the query contains a configured "
                              "brand term (options.brand_terms per site); absent "
                              "when no terms are configured"),
    ], description="search-query performance with branded/non-branded tagging"),
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


def tag_branded(rows: list[dict], brand_terms: list[str]) -> list[dict]:
    """Mark each query row branded/non-branded by substring match (in place)."""
    terms = [t.lower() for t in brand_terms]
    for row in rows:
        query = (row.get("query") or "").lower()
        row["branded"] = any(t in query for t in terms)
    return rows


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
        # sites may live under different Google logins (options.identities)
        site_urls = resolve_targets(self.settings.options, "site_urls", "site_url")
        groups = group_by_identity(site_urls, self.settings.options)
        self._creds = {ident: get_credentials(self.secrets_dir, identity=ident)
                       for ident in groups}
        self._groups = groups
        # refuse rather than silently query the wrong account if a re-login
        # ever swapped which real Google account this identity slot holds
        identity_emails = self.settings.options.get("identity_emails", {})
        labels = self.settings.options.get("labels", {})
        for ident, urls in groups.items():
            for url in urls:
                verify_identity_email(self.secrets_dir, ident,
                                      identity_emails.get(url), labels.get(url, url))

    def extract(self, date_from: date, date_to: date) -> Iterable[dict]:
        return self.extract_report("core", date_from, date_to)

    def extract_report(self, report: str, date_from: date,
                       date_to: date) -> Iterable[dict]:
        from googleapiclient.discovery import build

        registry = self.get_reports()[report]
        # unified name == native name for every GSC API dimension; computed
        # fields (native '_...') are filled locally, never sent to the API
        dims = tuple(s.name for s in registry.dimensions()
                     if not s.native.startswith("_"))
        labels = self.settings.options.get("labels", {})
        brand_terms: dict = self.settings.options.get("brand_terms", {})
        results: list[dict] = []
        for identity, site_urls in self._groups.items():
            service = build("searchconsole", "v1", credentials=self._creds[identity],
                            cache_discovery=False)
            results.extend(self._extract_sites(
                service, site_urls, dims, labels, brand_terms,
                report, date_from, date_to))
        return results

    def _extract_sites(self, service, site_urls, dims, labels, brand_terms,
                       report, date_from, date_to) -> list[dict]:
        results: list[dict] = []
        for site_url in site_urls:
            site_rows: list[dict] = []
            start_row = 0
            while True:
                body = {"startDate": date_from.isoformat(),
                        "endDate": date_to.isoformat(),
                        "dimensions": list(dims),
                        "rowLimit": _ROW_LIMIT, "startRow": start_row}
                resp = service.searchanalytics().query(
                    siteUrl=site_url, body=body).execute()
                page = resp.get("rows", [])
                site_rows.extend(parse_gsc_response(
                    resp, site_url, labels.get(site_url), dims))
                if len(page) < _ROW_LIMIT:
                    break
                start_row += _ROW_LIMIT
            if report == "queries" and brand_terms.get(site_url):
                tag_branded(site_rows, brand_terms[site_url])
            results.extend(site_rows)
        return results
