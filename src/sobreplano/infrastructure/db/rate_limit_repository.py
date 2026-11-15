"""PostgreSQL rate limit counters (table rate_limit_hits), one short transaction per call."""

from datetime import datetime, timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, case, delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from sobreplano.domain.errors import RateLimitStoreError
from sobreplano.domain.rate_limit import ClientUsage, WindowCounts, WindowKind
from sobreplano.infrastructure.db.models import RateLimitHitRow

_KEY = ["bucket", "window_kind", "client_key", "window_start"]


class SqlRateLimitRepository:
    """RateLimitRepository over its own sessions, never the request's.

    The request session never commits (FastAPI conventions), but a counter must be stored
    even when the request then fails, so each call opens, commits and closes its own.
    """

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def hit(
        self, bucket: str, client_key: str, minute_start: datetime, day_start: datetime
    ) -> WindowCounts:
        """Count one request in both windows with a single upsert and return both counts.

        Raises:
            RateLimitStoreError: if the database cannot be reached or the statement fails.
        """
        statement = (
            insert(RateLimitHitRow)
            .values(
                [
                    _row(bucket, WindowKind.MINUTE, client_key, minute_start),
                    _row(bucket, WindowKind.DAY, client_key, day_start),
                ]
            )
            # Row-level: two concurrent requests both count, the second waits for the first.
            .on_conflict_do_update(index_elements=_KEY, set_={"hits": RateLimitHitRow.hits + 1})
            .returning(RateLimitHitRow.window_kind, RateLimitHitRow.hits)
        )
        try:
            with self._session_factory() as session:
                rows = session.execute(statement).all()
                session.commit()
        except SQLAlchemyError as error:
            raise RateLimitStoreError(f"rate limit hit failed: {type(error).__name__}") from error
        counts = {kind: hits for kind, hits in rows}
        return WindowCounts(minute=counts[WindowKind.MINUTE], day=counts[WindowKind.DAY])

    def prune(self, before: datetime) -> int:
        """Delete windows that started before `before` and return how many.

        Raises:
            RateLimitStoreError: if the database cannot be reached or the statement fails.
        """
        statement = delete(RateLimitHitRow).where(RateLimitHitRow.window_start < before)
        try:
            with self._session_factory() as session:
                # A DELETE without RETURNING gives a CursorResult; Session.execute says Result.
                result = cast(CursorResult[Any], session.execute(statement))
                deleted = result.rowcount
                session.commit()
        except SQLAlchemyError as error:
            raise RateLimitStoreError(f"rate limit prune failed: {type(error).__name__}") from error
        return deleted

    def usage_since(self, since: datetime) -> list[ClientUsage]:
        """Usage per group and client: minute windows since `since`, days that overlap it.

        Raises:
            RateLimitStoreError: if the database cannot be reached or the statement fails.
        """
        is_minute = RateLimitHitRow.window_kind == WindowKind.MINUTE.value
        is_day = RateLimitHitRow.window_kind == WindowKind.DAY.value
        statement = (
            select(
                RateLimitHitRow.bucket,
                RateLimitHitRow.client_key,
                func.coalesce(func.sum(case((is_minute, RateLimitHitRow.hits))), 0),
                func.coalesce(func.max(case((is_minute, RateLimitHitRow.hits))), 0),
                func.coalesce(func.max(case((is_day, RateLimitHitRow.hits))), 0),
            )
            .where(
                or_(
                    is_minute & (RateLimitHitRow.window_start >= since),
                    # A day that started up to 24 hours before `since` still overlaps it.
                    is_day & (RateLimitHitRow.window_start > since - timedelta(days=1)),
                )
            )
            .group_by(RateLimitHitRow.bucket, RateLimitHitRow.client_key)
        )
        try:
            with self._session_factory() as session:
                rows = session.execute(statement).all()
        except SQLAlchemyError as error:
            raise RateLimitStoreError(
                f"rate limit report failed: {type(error).__name__}"
            ) from error
        return [
            ClientUsage(
                bucket=bucket,
                client_key=client_key,
                requests=int(requests),
                peak_minute=int(peak_minute),
                peak_day=int(peak_day),
            )
            for bucket, client_key, requests, peak_minute, peak_day in rows
        ]


def _row(bucket: str, kind: WindowKind, client_key: str, start: datetime) -> dict[str, object]:
    return {
        "bucket": bucket,
        "window_kind": kind.value,
        "client_key": client_key,
        "window_start": start,
        "hits": 1,
    }
