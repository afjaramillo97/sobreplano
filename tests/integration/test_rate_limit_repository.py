"""Rate limit counters against Postgres: one upsert per request, committed, safe under concurrency.

The repository commits on its own sessions, so these tests clean up their rows by client key.
"""

import threading
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import Engine, delete, event, select, text
from sqlalchemy.orm import Session, sessionmaker

from sobreplano.domain.errors import RateLimitStoreError
from sobreplano.domain.rate_limit import WindowCounts, windows_at
from sobreplano.infrastructure.db.engine import create_db_engine, create_session_factory
from sobreplano.infrastructure.db.models import RateLimitHitRow
from sobreplano.infrastructure.db.rate_limit_repository import SqlRateLimitRepository

pytestmark = pytest.mark.integration

NOW = datetime(2026, 11, 14, 15, 0, 20, tzinfo=UTC)
WINDOWS = windows_at(NOW)


@pytest.fixture
def factory(engine: Engine) -> sessionmaker[Session]:
    return create_session_factory(engine)


@pytest.fixture
def client_key(factory: sessionmaker[Session]) -> Iterator[str]:
    """A key no other test uses; its rows are deleted afterwards."""
    key = f"test-{uuid4().hex[:24]}"
    yield key
    with factory() as session:
        session.execute(delete(RateLimitHitRow).where(RateLimitHitRow.client_key == key))
        session.commit()


def hit(repository: SqlRateLimitRepository, client_key: str, now: datetime = NOW) -> WindowCounts:
    windows = windows_at(now)
    return repository.hit("detail", client_key, windows.minute_start, windows.day_start)


def test_hits_count_per_window_and_are_committed(
    factory: sessionmaker[Session], client_key: str
) -> None:
    repository = SqlRateLimitRepository(factory)
    assert hit(repository, client_key) == WindowCounts(minute=1, day=1)
    assert hit(repository, client_key) == WindowCounts(minute=2, day=2)
    # Next minute: a new minute window, the same day.
    assert hit(repository, client_key, NOW + timedelta(minutes=1)) == WindowCounts(minute=1, day=3)

    with factory() as session:  # another session sees them: they were committed
        rows = session.execute(
            select(RateLimitHitRow.window_kind, RateLimitHitRow.hits)
            .where(RateLimitHitRow.client_key == client_key)
            .order_by(RateLimitHitRow.window_kind, RateLimitHitRow.window_start)
        ).all()
    assert [tuple(row) for row in rows] == [("day", 3), ("minute", 2), ("minute", 1)]


def test_one_request_is_one_statement(
    engine: Engine, factory: sessionmaker[Session], client_key: str
) -> None:
    statements: list[str] = []

    def record(*args: object) -> None:
        statement = args[2]
        assert isinstance(statement, str)
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        hit(SqlRateLimitRepository(factory), client_key)
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert len(statements) == 1
    assert statements[0].lstrip().upper().startswith("INSERT")
    assert "ON CONFLICT" in statements[0].upper()


def test_two_concurrent_requests_both_count(
    factory: sessionmaker[Session], client_key: str
) -> None:
    repository = SqlRateLimitRepository(factory)
    barrier = threading.Barrier(2)
    results: list[WindowCounts] = []
    errors: list[BaseException] = []

    def request() -> None:
        try:
            barrier.wait()
            results.append(hit(repository, client_key))
        except BaseException as error:  # surfaced below; a thread cannot fail the test
            errors.append(error)

    threads = [threading.Thread(target=request) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert errors == []
    assert sorted(r.minute for r in results) == [1, 2]
    assert sorted(r.day for r in results) == [1, 2]


def test_the_forty_first_detail_of_a_day_is_counted_as_such(
    factory: sessionmaker[Session], client_key: str
) -> None:
    repository = SqlRateLimitRepository(factory)
    counts = [hit(repository, client_key, NOW + timedelta(minutes=i)) for i in range(41)]
    assert counts[-1] == WindowCounts(minute=1, day=41)


def test_prune_deletes_windows_older_than_the_cutoff(
    factory: sessionmaker[Session], client_key: str
) -> None:
    repository = SqlRateLimitRepository(factory)
    hit(repository, client_key, NOW - timedelta(days=3))
    hit(repository, client_key, NOW)
    deleted = repository.prune(NOW - timedelta(days=2))
    assert deleted >= 2  # the old minute and day windows (other keys may also go)
    with factory() as session:
        starts = session.scalars(
            select(RateLimitHitRow.window_start).where(RateLimitHitRow.client_key == client_key)
        ).all()
    assert all(start >= NOW - timedelta(days=2) for start in starts)
    assert len(starts) == 2


def test_usage_since_sums_minutes_and_keeps_the_peaks(
    factory: sessionmaker[Session], client_key: str
) -> None:
    repository = SqlRateLimitRepository(factory)
    for _ in range(3):
        hit(repository, client_key)
    hit(repository, client_key, NOW + timedelta(minutes=1))
    [usage] = [
        u for u in repository.usage_since(NOW - timedelta(hours=1)) if u.client_key == client_key
    ]
    assert (usage.bucket, usage.requests, usage.peak_minute, usage.peak_day) == ("detail", 4, 3, 4)


def test_the_stored_key_is_whatever_hash_the_caller_gives(
    factory: sessionmaker[Session], client_key: str
) -> None:
    hit(SqlRateLimitRepository(factory), client_key)
    with factory() as session:
        stored = (
            session.execute(
                text("SELECT client_key FROM rate_limit_hits WHERE client_key = :key"),
                {"key": client_key},
            )
            .scalars()
            .all()
        )
    assert stored == [client_key, client_key]


def test_an_unreachable_database_raises_the_store_error() -> None:
    engine = create_db_engine("postgresql+psycopg://unused@127.0.0.1:1/unused")
    repository = SqlRateLimitRepository(create_session_factory(engine))
    with pytest.raises(RateLimitStoreError):
        repository.hit("detail", "k", WINDOWS.minute_start, WINDOWS.day_start)
    engine.dispose()
