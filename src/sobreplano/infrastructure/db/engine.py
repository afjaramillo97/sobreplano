"""SQLAlchemy engine and session factory built from DATABASE_URL."""

from typing import Any

from pydantic import ValidationError
from sqlalchemy import Engine, create_engine, make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from sobreplano.infrastructure.settings import load_settings

# Supabase's shared pooler in transaction mode. It hands each transaction to
# any backend connection, so server-side prepared statements break there.
TRANSACTION_POOLER_PORT = 6543


def get_database_url() -> str:
    """Return DATABASE_URL from the environment.

    Raises:
        RuntimeError: if DATABASE_URL is not set.
    """
    try:
        return load_settings().database_url
    except ValidationError as error:
        raise RuntimeError("DATABASE_URL is not set; copy .env.example to .env") from error


def engine_options(url: str, *, null_pool: bool = False) -> dict[str, Any]:
    """Return the create_engine keyword arguments for url.

    Turns psycopg prepared statements off when url points at the transaction
    pooler, and adds NullPool when null_pool is true.
    """
    options: dict[str, Any] = {}
    if make_url(url).port == TRANSACTION_POOLER_PORT:
        options["connect_args"] = {"prepare_threshold": None}
    if null_pool:
        # In a frozen Lambda a pooled connection outlives the invocation and
        # hangs; Supabase's pooler already reuses connections for us.
        options["poolclass"] = NullPool
    return options


def create_db_engine(url: str | None = None, *, null_pool: bool = False) -> Engine:
    """Create a synchronous engine for url, or for DATABASE_URL when url is None.

    See engine_options for the transaction-pooler and null_pool settings.
    """
    resolved = url or get_database_url()
    return create_engine(resolved, **engine_options(resolved, null_pool=null_pool))


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a session factory for engine.

    expire_on_commit is off so entities stay readable after the caller commits.
    """
    return sessionmaker(engine, expire_on_commit=False)
