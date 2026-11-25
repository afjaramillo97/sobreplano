"""Unit tests for the rate limit windows (minute, Bogotá day) and the limit check."""

from datetime import UTC, datetime

from sobreplano.domain.rate_limit import (
    BOGOTA,
    Exceeded,
    Limit,
    Remaining,
    WindowCounts,
    WindowKind,
    check_limit,
    remaining,
    windows_at,
)

LIMIT = Limit(per_minute=10, per_day=40)


def test_the_minute_window_is_the_minute_that_contains_now() -> None:
    windows = windows_at(datetime(2026, 11, 14, 15, 7, 42, 500, tzinfo=UTC))
    assert windows.minute_start == datetime(2026, 11, 14, 15, 7, tzinfo=UTC)
    assert windows.minute_end == datetime(2026, 11, 14, 15, 8, tzinfo=UTC)


def test_the_day_is_the_bogota_calendar_day_not_the_utc_one() -> None:
    # 04:59 UTC on the 15th is still 23:59 of the 14th in Bogotá (UTC-5).
    late = windows_at(datetime(2026, 11, 15, 4, 59, tzinfo=UTC))
    assert late.day_start == datetime(2026, 11, 14, tzinfo=BOGOTA)
    assert late.day_end == datetime(2026, 11, 15, tzinfo=BOGOTA)
    # One minute later the day changes.
    assert windows_at(datetime(2026, 11, 15, 5, 0, tzinfo=UTC)).day_start == datetime(
        2026, 11, 15, tzinfo=BOGOTA
    )


def test_counts_within_the_limit_pass() -> None:
    now = datetime(2026, 11, 14, 15, 7, 20, tzinfo=UTC)
    assert check_limit(WindowCounts(minute=10, day=40), LIMIT, windows_at(now), now) is None


def test_over_the_minute_limit_waits_until_the_next_minute() -> None:
    now = datetime(2026, 11, 14, 15, 7, 20, tzinfo=UTC)
    exceeded = check_limit(WindowCounts(minute=11, day=11), LIMIT, windows_at(now), now)
    assert exceeded == Exceeded(WindowKind.MINUTE, 40)


def test_over_the_day_limit_waits_until_bogota_midnight_even_if_the_minute_is_also_over() -> None:
    now = datetime(2026, 11, 14, 23, 0, tzinfo=UTC)  # 18:00 in Bogotá
    exceeded = check_limit(WindowCounts(minute=11, day=41), LIMIT, windows_at(now), now)
    assert exceeded == Exceeded(WindowKind.DAY, 6 * 3600)


def test_retry_after_is_at_least_one_second() -> None:
    now = datetime(2026, 11, 14, 15, 7, 59, 999_999, tzinfo=UTC)
    exceeded = check_limit(WindowCounts(minute=11, day=11), LIMIT, windows_at(now), now)
    assert exceeded is not None
    assert exceeded.retry_after_seconds == 1


def test_remaining_is_what_is_left_of_each_window() -> None:
    assert remaining(WindowCounts(minute=3, day=12), LIMIT) == Remaining(minute=7, day=28)


def test_remaining_never_goes_below_zero() -> None:
    assert remaining(WindowCounts(minute=11, day=41), LIMIT) == Remaining(minute=0, day=0)
