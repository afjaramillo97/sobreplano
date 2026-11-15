"""Report the clients that made the most requests in the last 24 hours, per group of routes."""

import argparse
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from pydantic import ValidationError

from sobreplano.domain.errors import RateLimitStoreError
from sobreplano.domain.rate_limit import ClientUsage, Limit
from sobreplano.infrastructure.db.engine import create_db_engine, create_session_factory
from sobreplano.infrastructure.db.rate_limit_repository import SqlRateLimitRepository
from sobreplano.infrastructure.settings import load_settings
from sobreplano.interface.api.rate_limit import Bucket, limits_from

TOP = 10
PERIOD = timedelta(hours=24)
SHORT_KEY = 8  # as in the rate_limited log line


def went_over(usage: ClientUsage, limit: Limit) -> bool:
    """Whether the client passed its group's limit in some minute or day."""
    return usage.peak_minute > limit.per_minute or usage.peak_day > limit.per_day


def format_report(usages: Sequence[ClientUsage], group_limits: dict[Bucket, Limit]) -> str:
    """Per group: how many clients went over, then the TOP clients by requests."""
    lines: list[str] = []
    for bucket in Bucket:
        group = sorted(
            (u for u in usages if u.bucket == bucket), key=lambda u: u.requests, reverse=True
        )
        limit = group_limits[bucket]
        over = sum(went_over(u, limit) for u in group)
        lines.append(
            f"{bucket} (limit {limit.per_minute}/min, {limit.per_day}/day): "
            f"{len(group)} clients, {over} over the limit"
        )
        for usage in group[:TOP]:
            flag = "  OVER" if went_over(usage, limit) else ""
            lines.append(
                f"  {usage.client_key[:SHORT_KEY]}  {usage.requests:>6} requests"
                f"  peak {usage.peak_minute}/min  {usage.peak_day}/day{flag}"
            )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """Print the report; exits 2 on bad configuration and 1 if the database fails."""
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    try:
        settings = load_settings()
    except ValidationError as error:
        print(f"bad configuration: {error}")
        return 2
    since = datetime.now(UTC) - PERIOD
    engine = create_db_engine(settings.database_url)
    try:
        usages = SqlRateLimitRepository(create_session_factory(engine)).usage_since(since)
    except RateLimitStoreError as error:
        print(f"report failed: {error}")
        return 1
    finally:
        engine.dispose()
    print(f"since {since:%Y-%m-%d %H:%M} UTC")
    print(format_report(usages, limits_from(settings)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
