"""Time helpers: timezone-aware UTC timestamps and APP_TIMEZONE day boundaries."""
from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from ..config import get_settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def app_tz() -> ZoneInfo:
    return ZoneInfo(get_settings().app_timezone)


def local_today(now: datetime | None = None) -> date:
    """Current calendar date in APP_TIMEZONE (backend-owned limit date)."""
    if now is None:
        now = utcnow()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(app_tz()).date()
