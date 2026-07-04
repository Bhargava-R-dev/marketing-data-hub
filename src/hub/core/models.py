from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

CORE_DIMENSIONS = ["date", "source", "account_id", "account_name", "campaign_id", "campaign"]
CORE_METRICS = ["impressions", "clicks", "spend", "conversions", "conversion_value", "sessions", "users"]
CORE_FIELDS = set(CORE_DIMENSIONS) | set(CORE_METRICS)


class UnifiedRow(BaseModel):
    date: date
    source: str
    account_id: str
    account_name: str = ""
    campaign_id: str | None = None
    campaign: str | None = None
    impressions: int | None = None
    clicks: int | None = None
    spend: float | None = None
    conversions: float | None = None
    conversion_value: float | None = None
    sessions: int | None = None
    users: int | None = None
    extras: dict = Field(default_factory=dict)

    @field_validator("account_id", "campaign_id", mode="before")
    @classmethod
    def _ids_to_str(cls, v):
        return str(v) if isinstance(v, int) else v


class SyncRun(BaseModel):
    id: int | None = None
    source: str
    started_at: datetime
    finished_at: datetime | None = None
    date_from: date
    date_to: date
    rows_written: int = 0
    status: str = "running"  # running | success | error
    error_message: str | None = None
