"""Delete rate limit windows older than 2 days; SPEC 12 schedules it."""

import argparse
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from pydantic import ValidationError

from sobreplano.domain.errors import RateLimitStoreError
from sobreplano.infrastructure.db.engine import create_db_engine, create_session_factory
from sobreplano.infrastructure.db.rate_limit_repository import SqlRateLimitRepository
from sobreplano.infrastructure.settings import load_settings

# Two days keep yesterday's whole day window for the report; IP hashes go no further.
RETENTION = timedelta(days=2)


def main(argv: Sequence[str] | None = None) -> int:
    """Prune old windows; exits 2 on bad configuration and 1 if the database fails."""
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    try:
        settings = load_settings()
    except ValidationError as error:
        print(f"bad configuration: {error}")
        return 2
    cutoff = datetime.now(UTC) - RETENTION
    engine = create_db_engine(settings.database_url)
    try:
        deleted = SqlRateLimitRepository(create_session_factory(engine)).prune(cutoff)
    except RateLimitStoreError as error:
        print(f"prune failed: {error}")
        return 1
    finally:
        engine.dispose()
    print(f"{deleted} rate limit windows deleted (started before {cutoff:%Y-%m-%d %H:%M} UTC)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
