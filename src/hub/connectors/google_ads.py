from __future__ import annotations

import json
from datetime import date
from typing import Iterable

from hub.connectors.base import AuthError, BaseConnector, FieldRegistry, FieldSpec

GOOGLE_ADS_FIELDS = FieldRegistry([
    FieldSpec("date", "segments.date", dimension=True),
    FieldSpec("campaign_id", "campaign.id", dimension=True),
    FieldSpec("campaign", "campaign.name", dimension=True),
    FieldSpec("impressions", "metrics.impressions"),
    FieldSpec("clicks", "metrics.clicks"),
    FieldSpec("spend", "metrics.cost_micros", description="cost_micros / 1e6"),
    FieldSpec("conversions", "metrics.conversions"),
    FieldSpec("conversion_value", "metrics.conversions_value"),
])

_GAQL = """
    SELECT segments.date, campaign.id, campaign.name, metrics.impressions,
           metrics.clicks, metrics.cost_micros, metrics.conversions,
           metrics.conversions_value
    FROM campaign
    WHERE segments.date BETWEEN '{start}' AND '{end}'
"""


def parse_google_ads_rows(rows: list[dict], customer_id: str) -> list[dict]:
    out = []
    for row in rows:
        out.append({
            "account_id": customer_id,
            "account_name": f"Google Ads {customer_id}",
            "date": row["segments.date"],
            "campaign_id": str(row["campaign.id"]),
            "campaign": row["campaign.name"],
            "impressions": row["metrics.impressions"],
            "clicks": row["metrics.clicks"],
            "spend": row["metrics.cost_micros"] / 1_000_000,
            "conversions": row["metrics.conversions"],
            "conversion_value": row["metrics.conversions_value"],
        })
    return out


class GoogleAdsConnector(BaseConnector):
    id = "google_ads"
    fields = GOOGLE_ADS_FIELDS

    def authenticate(self) -> None:
        opts = self.settings.options
        if not opts.get("developer_token"):
            raise AuthError(
                "Google Ads connector is not activated.",
                hint=("Apply for a developer_token at ads.google.com > Tools > "
                      "API Center, then add developer_token, customer_id and "
                      "login_customer_id under connectors.google_ads.options "
                      "in config.yaml."))
        token_path = self.secrets_dir / "google_token.json"
        client_path = self.secrets_dir / "google_client.json"
        if not token_path.exists() or not client_path.exists():
            raise AuthError(
                "Google OAuth files missing.",
                hint="Run a sync of ga4/gsc first to create secrets/google_token.json.")
        token = json.loads(token_path.read_text(encoding="utf-8"))
        client = json.loads(client_path.read_text(encoding="utf-8"))
        installed = client.get("installed") or client.get("web") or {}
        self._ads_config = {
            "developer_token": opts["developer_token"],
            "client_id": installed.get("client_id") or token.get("client_id"),
            "client_secret": installed.get("client_secret") or token.get("client_secret"),
            "refresh_token": token["refresh_token"],
            "login_customer_id": str(opts.get("login_customer_id", opts["customer_id"])).replace("-", ""),
            "use_proto_plus": True,
        }

    def extract(self, date_from: date, date_to: date) -> Iterable[dict]:
        from google.ads.googleads.client import GoogleAdsClient

        customer_id = str(self.settings.options["customer_id"]).replace("-", "")
        client = GoogleAdsClient.load_from_dict(self._ads_config)
        service = client.get_service("GoogleAdsService")
        query = _GAQL.format(start=date_from.isoformat(), end=date_to.isoformat())
        flat_rows = []
        for batch in service.search_stream(customer_id=customer_id, query=query):
            for row in batch.results:
                flat_rows.append({
                    "segments.date": row.segments.date,
                    "campaign.id": row.campaign.id,
                    "campaign.name": row.campaign.name,
                    "metrics.impressions": row.metrics.impressions,
                    "metrics.clicks": row.metrics.clicks,
                    "metrics.cost_micros": row.metrics.cost_micros,
                    "metrics.conversions": row.metrics.conversions,
                    "metrics.conversions_value": row.metrics.conversions_value,
                })
        return parse_google_ads_rows(flat_rows, self.settings.options["customer_id"])
