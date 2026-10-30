"""SQLAlchemy engine and session factory built from DATABASE_URL."""

from pydantic import ValidationError
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from sobreplano.infrastructure.settings import load_settings


def get_database_url() -> str:
    """Return DATABASE_URL from the environment.

    Raises:
        RuntimeError: if DATABASE_URL is not set.
    """
    try:
        return load_settings().database_url
    except ValidationError as error:
        raise RuntimeError("DATABASE_URL is not set; copy .env.example to .env") from error


def create_db_engine(url: str | None = None) -> Engine:
    """Create a synchronous engine for url, or for DATABASE_URL when url is None."""
    return create_engine(url or get_database_url())


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a session factory for engine.

    expire_on_commit is off so entities stay readable after the caller commits.
    """
    return sessionmaker(engine, expire_on_commit=False)
