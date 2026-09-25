"""Shared timestamp rules for the API and Lab business calendar."""

from datetime import datetime, timedelta, timezone
from typing import Optional


# Thailand has no daylight-saving changes, so a fixed UTC+7 offset is enough
# for Lab wall-clock rules while keeping all stored instants in UTC.
LAB_TIMEZONE = timezone(timedelta(hours=7), name="Asia/Bangkok")
UTC = timezone.utc


def utc_now() -> datetime:
    """Return the current instant as an aware UTC datetime."""

    return datetime.now(UTC)


def lab_now() -> datetime:
    """Return the current instant in the Lab's business timezone."""

    return utc_now().astimezone(LAB_TIMEZONE)


def lab_now_naive() -> datetime:
    """Return Lab wall-clock time without tzinfo for date/time-only rules."""

    return lab_now().replace(tzinfo=None)


def as_utc(
    value: Optional[datetime],
    *,
    naive_timezone: timezone = LAB_TIMEZONE,
) -> Optional[datetime]:
    """Normalize an aware or legacy naive datetime to aware UTC.

    Older Agent payloads contain naive timestamps. They were generated on Lab
    workstations, so they are interpreted as Lab local time for compatibility.
    """

    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=naive_timezone)
    return value.astimezone(UTC)


def as_lab_naive(value: Optional[datetime]) -> Optional[datetime]:
    """Convert an instant to Lab wall-clock time without tzinfo."""

    normalized = as_utc(value)
    if normalized is None:
        return None
    return normalized.astimezone(LAB_TIMEZONE).replace(tzinfo=None)
