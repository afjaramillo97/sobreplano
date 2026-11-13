"""Postgres checkpointer for the advisor's memory, on one psycopg connection per use."""

from collections.abc import Generator
from contextlib import contextmanager

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import DictRow, dict_row


def psycopg_url(database_url: str) -> str:
    """DATABASE_URL without SQLAlchemy's driver suffix, as psycopg expects it."""
    return database_url.replace("postgresql+psycopg://", "postgresql://", 1)


@contextmanager
def open_checkpointer(database_url: str) -> Generator[PostgresSaver]:
    """A PostgresSaver on a new connection, closed on exit.

    setup() is never called: migration 0007 owns the checkpointer tables (and their RLS).
    Autocommit, as the library requires; prepare_threshold=None because the Supabase pooler in
    transaction mode breaks server-side prepared statements, as in the SQLAlchemy engine.
    """
    with psycopg.Connection[DictRow].connect(
        psycopg_url(database_url),
        autocommit=True,
        prepare_threshold=None,
        row_factory=dict_row,
    ) as connection:
        yield PostgresSaver(connection)
