"""Quiet-hours calculations. Default timezone is Asia/Colombo."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo


def parse_hhmm(value: str) -> time:
    parts = value.strip().split(":")
    if len(parts) != 2:
        raise ValueError("quiet hours must be HH:MM")
    try:
        hour, minute = (int(part) for part in parts)
    except ValueError as exc:
        raise ValueError("quiet hours must be HH:MM") from exc
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("quiet hours must be a valid 24-hour time")
    return time(hour=hour, minute=minute)


def _as_utc(now: datetime) -> datetime:
    return now.replace(tzinfo=UTC) if now.tzinfo is None else now.astimezone(UTC)


def _naive(value: time) -> time:
    return value.replace(tzinfo=None)


def _window_end(local: datetime, end: time) -> datetime:
    candidate = datetime.combine(local.date(), end, tzinfo=local.tzinfo)
    if candidate <= local:
        candidate += timedelta(days=1)
    return candidate


def is_quiet(now: datetime, start: time | None, end: time | None, tz_name: str) -> bool:
    if start is None or end is None:
        return False
    start = _naive(start)
    end = _naive(end)
    if start == end:
        return False
    local = _as_utc(now).astimezone(ZoneInfo(tz_name))
    current = local.time()
    if start < end:
        return start <= current < end
    return current >= start or current < end


def next_quiet_end(now: datetime, start: time | None, end: time | None, tz_name: str) -> datetime:
    """Return the next window end as an aware UTC datetime.

    If quiet hours are disabled or currently inactive, this returns the next
    boundary (today or tomorrow) so callers can use it as a safe retry time.
    """
    if start is None or end is None or start == end:
        return _as_utc(now)
    start = _naive(start)
    end = _naive(end)
    local = _as_utc(now).astimezone(ZoneInfo(tz_name))
    current = local.time()
    if start < end:
        if current < end:
            candidate = datetime.combine(local.date(), end, tzinfo=local.tzinfo)
        else:
            candidate = datetime.combine(local.date() + timedelta(days=1), end, tzinfo=local.tzinfo)
    else:
        if current >= start:
            candidate = datetime.combine(local.date() + timedelta(days=1), end, tzinfo=local.tzinfo)
        else:
            candidate = datetime.combine(local.date(), end, tzinfo=local.tzinfo)
    return candidate.astimezone(UTC)
