from __future__ import annotations

from datetime import UTC, datetime, time

from app.utils.quiet_hours import is_quiet, next_quiet_end, parse_hhmm


def _colombo(hour: int, minute: int = 0, day: int = 26) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=UTC)  # approx; uses conversion below


def test_parse_hhmm():
    assert parse_hhmm("21:30") == time(21, 30)


def test_daytime_window_inside_and_outside():
    start, end = time(9, 0), time(17, 0)
    inside = datetime(2026, 11, 26, 6, 0, tzinfo=UTC)  # 11:30 Colombo
    outside = datetime(2026, 11, 26, 14, 0, tzinfo=UTC)  # 19:30 Colombo
    assert is_quiet(inside, start, end, "Asia/Colombo")
    assert not is_quiet(outside, start, end, "Asia/Colombo")


def test_overnight_window():
    start, end = time(21, 0), time(7, 0)
    late = datetime(2026, 11, 26, 17, 0, tzinfo=UTC)  # 22:30 Colombo
    early = datetime(2026, 11, 26, 1, 0, tzinfo=UTC)  # 06:30 Colombo
    midday = datetime(2026, 11, 26, 6, 30, tzinfo=UTC)  # 12:00 Colombo
    assert is_quiet(late, start, end, "Asia/Colombo")
    assert is_quiet(early, start, end, "Asia/Colombo")
    assert not is_quiet(midday, start, end, "Asia/Colombo")


def test_equal_boundaries_disable_quiet_hours():
    value = datetime(2026, 11, 26, 17, 0, tzinfo=UTC)
    assert not is_quiet(value, time(9, 0), time(9, 0), "Asia/Colombo")


def test_next_quiet_end_for_overnight():
    late = datetime(2026, 11, 26, 17, 0, tzinfo=UTC)  # 22:30 Colombo
    end = next_quiet_end(late, time(21, 0), time(7, 0), "Asia/Colombo")
    assert end == datetime(2026, 11, 27, 1, 30, tzinfo=UTC)  # 07:00 Colombo


def test_next_quiet_end_for_daytime_before_window():
    early = datetime(2026, 11, 26, 3, 0, tzinfo=UTC)  # 08:30 Colombo
    end = next_quiet_end(early, time(9, 0), time(17, 0), "Asia/Colombo")
    assert end == datetime(2026, 11, 26, 11, 30, tzinfo=UTC)  # 17:00 Colombo
