from __future__ import annotations

from datetime import date
from typing import Iterable

from hub.connectors.base import BaseConnector, FieldRegistry, FieldSpec
from hub.connectors.google_auth import get_credentials

YOUTUBE_FIELDS = FieldRegistry([
    FieldSpec("date", "day", dimension=True),
    FieldSpec("views", "views"),
    FieldSpec("likes", "likes"),
    FieldSpec("watch_minutes", "estimatedMinutesWatched"),
    FieldSpec("subscribers_gained", "subscribersGained"),
])

_N2U = YOUTUBE_FIELDS.native_to_unified()


def parse_youtube_response(resp: dict, channel_id: str) -> list[dict]:
    headers = [h["name"] for h in resp.get("columnHeaders", [])]
    out = []
    for row in resp.get("rows", []):
        raw = {"account_id": channel_id, "account_name": f"YouTube {channel_id}"}
        for name, value in zip(headers, row):
            raw[_N2U[name]] = value
        out.append(raw)
    return out


class YouTubeConnector(BaseConnector):
    id = "youtube"
    fields = YOUTUBE_FIELDS

    def authenticate(self) -> None:
        self._creds = get_credentials(self.secrets_dir)

    def extract(self, date_from: date, date_to: date) -> Iterable[dict]:
        from googleapiclient.discovery import build

        channel_id = self.settings.options.get("channel_id", "mine")
        ids = "channel==MINE" if channel_id == "mine" else f"channel=={channel_id}"
        service = build("youtubeAnalytics", "v2", credentials=self._creds,
                        cache_discovery=False)
        resp = service.reports().query(
            ids=ids, startDate=date_from.isoformat(), endDate=date_to.isoformat(),
            metrics="views,likes,estimatedMinutesWatched,subscribersGained",
            dimensions="day", sort="day").execute()
        return parse_youtube_response(resp, channel_id)
