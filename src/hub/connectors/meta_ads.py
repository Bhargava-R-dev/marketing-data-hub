from __future__ import annotations

from datetime import date
from typing import Iterable

from hub.connectors.base import AuthError, BaseConnector, FieldRegistry, FieldSpec

META_FIELDS = FieldRegistry([
    FieldSpec("date", "date_start", dimension=True),
    FieldSpec("campaign_id", "campaign_id", dimension=True),
    FieldSpec("campaign", "campaign_name", dimension=True),
    FieldSpec("impressions", "impressions"),
    FieldSpec("clicks", "clicks"),
    FieldSpec("spend", "spend"),
    FieldSpec("conversions", "actions",
              description="sum of configured conversion_actions"),
])

DEFAULT_CONVERSION_ACTIONS = ["purchase", "lead", "offsite_conversion.fb_pixel_purchase"]


def parse_meta_insights(rows: list[dict], account_id: str,
                        conversion_actions: list[str] | None = None) -> list[dict]:
    actions_wanted = conversion_actions or DEFAULT_CONVERSION_ACTIONS
    out = []
    for row in rows:
        conversions = sum(
            float(a["value"]) for a in row.get("actions", [])
            if a.get("action_type") in actions_wanted)
        out.append({
            "account_id": account_id, "account_name": f"Meta {account_id}",
            "date": row["date_start"],
            "campaign_id": row.get("campaign_id"),
            "campaign": row.get("campaign_name"),
            "impressions": row.get("impressions"),
            "clicks": row.get("clicks"),
            "spend": row.get("spend"),
            "conversions": conversions,
        })
    return out


class MetaAdsConnector(BaseConnector):
    id = "meta_ads"
    fields = META_FIELDS

    def authenticate(self) -> None:
        opts = self.settings.options
        if not opts.get("access_token") or not opts.get("ad_account_id"):
            raise AuthError(
                "Meta Ads connector is not activated.",
                hint=("Create a Meta app at developers.facebook.com, generate a "
                      "long-lived access_token with ads_read permission, and add "
                      "access_token + ad_account_id (act_...) under "
                      "connectors.meta_ads.options in config.yaml."))

    def extract(self, date_from: date, date_to: date) -> Iterable[dict]:
        from facebook_business.adobjects.adaccount import AdAccount
        from facebook_business.api import FacebookAdsApi

        opts = self.settings.options
        FacebookAdsApi.init(access_token=opts["access_token"])
        account = AdAccount(opts["ad_account_id"])
        insights = account.get_insights(
            fields=["campaign_id", "campaign_name", "impressions", "clicks",
                    "spend", "actions"],
            params={"level": "campaign", "time_increment": 1,
                    "time_range": {"since": date_from.isoformat(),
                                   "until": date_to.isoformat()}})
        rows = [dict(i) for i in insights]
        return parse_meta_insights(rows, opts["ad_account_id"],
                                   opts.get("conversion_actions"))
