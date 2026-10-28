"""SQLAlchemy engine and session factory built from DATABASE_URL."""

import os

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def get_database_url() -> str:
    """Return DATABASE_URL from the environment.

    Raises:
        RuntimeError: if DATABASE_URL is not set.
    """
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set; copy .env.example to .env")
    return url


def create_db_engine(url: str | None = None) -> Engine:
    """Create a synchronous engine for url, or for DATABASE_URL when url is None."""
    return create_engine(url or get_database_url())


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a session factory for engine.

    expire_on_commit is off so entities stay readable after the caller commits.
    """
    return sessionmaker(engine, expire_on_commit=False)
