"""Delete advisor conversations without messages in 7 days: checkpoints and their row."""

import argparse
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from pydantic import ValidationError

from sobreplano.infrastructure.advisor.checkpointer import open_checkpointer
from sobreplano.infrastructure.db.advisor_thread_repository import SqlAdvisorThreadRepository
from sobreplano.infrastructure.db.engine import create_db_engine, create_session_factory
from sobreplano.infrastructure.settings import load_settings

RETENTION_DAYS = 7


def main(argv: Sequence[str] | None = None) -> int:
    """Delete (or with --dry-run only count) inactive conversations; exits 2 on bad config."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="count, do not delete")
    args = parser.parse_args(argv)

    try:
        settings = load_settings()
    except ValidationError as error:
        print(f"bad configuration: {error}")
        return 2
    cutoff = datetime.now(UTC) - timedelta(days=RETENTION_DAYS)
    session_factory = create_session_factory(create_db_engine(settings.database_url))

    with session_factory() as session:
        threads = SqlAdvisorThreadRepository(session)
        inactive = threads.list_inactive_since(cutoff)
        if args.dry_run:
            print(f"{len(inactive)} conversations inactive since {cutoff:%Y-%m-%d %H:%M} UTC")
            return 0
        with open_checkpointer(settings.database_url) as checkpointer:
            for thread_id in inactive:
                # Checkpoints first (autocommit): if this stops halfway, the row is still there
                # and the next run deletes the rest; delete_thread is idempotent.
                checkpointer.delete_thread(str(thread_id))
                threads.delete(thread_id)
                session.commit()
    print(f"{len(inactive)} conversations deleted (inactive since {cutoff:%Y-%m-%d %H:%M} UTC)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
