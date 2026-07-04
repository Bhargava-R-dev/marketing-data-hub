from __future__ import annotations

from datetime import date
from typing import Iterable

from hub.connectors.base import BaseConnector, FieldRegistry, FieldSpec
from hub.connectors.google_auth import get_credentials

GSC_FIELDS = FieldRegistry([
    FieldSpec("date", "date", dimension=True),
    FieldSpec("clicks", "clicks"),
    FieldSpec("impressions", "impressions"),
    FieldSpec("ctr", "ctr", description="click-through rate (extras)"),
    FieldSpec("position", "position", description="avg SERP position (extras)"),
])


def parse_gsc_response(resp: dict, site_url: str) -> list[dict]:
    out = []
    for row in resp.get("rows", []):
        out.append({
            "account_id": site_url, "account_name": site_url,
            "date": row["keys"][0],
            "clicks": row.get("clicks"), "impressions": row.get("impressions"),
            "ctr": row.get("ctr"), "position": row.get("position"),
        })
    return out


class SearchConsoleConnector(BaseConnector):
    id = "gsc"
    fields = GSC_FIELDS

    def authenticate(self) -> None:
        self._creds = get_credentials(self.secrets_dir)

    def extract(self, date_from: date, date_to: date) -> Iterable[dict]:
        from googleapiclient.discovery import build

        site_url = self.settings.options["site_url"]
        service = build("searchconsole", "v1", credentials=self._creds,
                        cache_discovery=False)
        body = {"startDate": date_from.isoformat(), "endDate": date_to.isoformat(),
                "dimensions": ["date"], "rowLimit": 25000}
        resp = service.searchanalytics().query(siteUrl=site_url, body=body).execute()
        return parse_gsc_response(resp, site_url)
