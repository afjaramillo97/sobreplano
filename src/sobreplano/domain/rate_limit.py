"""Rate limit windows: per minute and per Bogotá day, and whether a count goes over a limit."""

import math
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

BOGOTA = ZoneInfo("America/Bogota")


class WindowKind(StrEnum):
    """The two fixed windows every request is counted in."""

    MINUTE = "minute"
    DAY = "day"


@dataclass(frozen=True)
class Windows:
    """Start and end of the minute and of the Bogotá day that contain one instant."""

    minute_start: datetime
    minute_end: datetime
    day_start: datetime
    day_end: datetime


def windows_at(now: datetime) -> Windows:
    """The windows that contain now, which must be timezone-aware.

    The day is the calendar day in America/Bogota (no daylight saving), as for the
    advisor's budget, so it resets at local midnight and not at 19:00.
    """
    minute_start = now.replace(second=0, microsecond=0)
    day_start = datetime.combine(now.astimezone(BOGOTA).date(), time(), BOGOTA)
    return Windows(
        minute_start=minute_start,
        minute_end=minute_start + timedelta(minutes=1),
        day_start=day_start,
        day_end=day_start + timedelta(days=1),
    )


@dataclass(frozen=True)
class Limit:
    """Most requests one client may make per minute and per day."""

    per_minute: int
    per_day: int


@dataclass(frozen=True)
class WindowCounts:
    """Requests of one client counted so far in each window, this one included."""

    minute: int
    day: int


@dataclass(frozen=True)
class Exceeded:
    """The window a request went over, and the seconds until that window ends."""

    window: WindowKind
    retry_after_seconds: int


def check_limit(
    counts: WindowCounts, limit: Limit, windows: Windows, now: datetime
) -> Exceeded | None:
    """None if counts are within limit, else the window that was exceeded.

    When both are, the day wins: waiting for the next minute would not help.
    """
    if counts.day > limit.per_day:
        return Exceeded(WindowKind.DAY, _seconds_until(windows.day_end, now))
    if counts.minute > limit.per_minute:
        return Exceeded(WindowKind.MINUTE, _seconds_until(windows.minute_end, now))
    return None


@dataclass(frozen=True)
class ClientUsage:
    """What one client did in one group of routes over a period, for the report."""

    bucket: str
    client_key: str
    requests: int  # sum of its minute windows
    peak_minute: int  # most requests in one minute
    peak_day: int  # most requests in one day


def _seconds_until(end: datetime, now: datetime) -> int:
    return max(1, math.ceil((end - now).total_seconds()))
