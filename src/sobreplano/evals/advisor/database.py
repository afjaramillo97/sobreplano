"""Isolated evals database: created from scratch on the local server, migrated and seeded."""

import os
import re
import subprocess
import sys
from pathlib import Path

from sqlalchemy import URL, make_url, text
from sqlalchemy.orm import Session

from sobreplano.infrastructure.db.engine import create_db_engine
from sobreplano.interface.cli.seed import SeedReport, load_seed, run_seed

DEFAULT_EVAL_DATABASE_URL = (
    "postgresql+psycopg://postgres:postgres@127.0.0.1:54322/sobreplano_evals"
)
CATALOG_PATH = Path("evals/advisor/catalog.json")
ALEMBIC_INI = Path("alembic.ini")

LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost"})
# The development database and Postgres' own databases are never dropped.
PROTECTED_DATABASES = frozenset({"postgres", "template0", "template1"})
# The name goes into DROP/CREATE DATABASE, which take no bind parameters.
DATABASE_NAME = re.compile(r"^[a-z_][a-z0-9_]*$")


class UnsafeEvalDatabaseError(Exception):
    """The evals database URL points somewhere the fictitious catalog must never go."""


def eval_database_url() -> str:
    """EVAL_DATABASE_URL, or the local default."""
    return os.environ.get("EVAL_DATABASE_URL") or DEFAULT_EVAL_DATABASE_URL


def check_local(url: str) -> URL:
    """Parse url and make sure it is a disposable database on this machine.

    Raises:
        UnsafeEvalDatabaseError: if the host is not 127.0.0.1 or localhost, or the database
            name is missing, protected or not a plain lowercase identifier.
    """
    parsed = make_url(url)
    if parsed.host not in LOCAL_HOSTS:
        raise UnsafeEvalDatabaseError(
            f"evals database host must be one of {sorted(LOCAL_HOSTS)}, got {parsed.host!r}"
        )
    name = parsed.database or ""
    if name in PROTECTED_DATABASES or not DATABASE_NAME.match(name):
        raise UnsafeEvalDatabaseError(f"refusing to recreate database {name!r}")
    return parsed


def prepare(url: str, catalog: Path = CATALOG_PATH) -> SeedReport:
    """Drop and recreate the evals database, migrate it to head and load the catalog.

    Raises:
        UnsafeEvalDatabaseError: before touching anything, if url is not a local
            disposable database (see check_local).
        FileNotFoundError, pydantic.ValidationError: if the catalog cannot be read.
        subprocess.CalledProcessError: if a migration fails.
    """
    target = check_local(url)
    seed = load_seed(catalog)  # validate before dropping anything
    name = target.database
    admin = create_db_engine(target.set(database="postgres").render_as_string(hide_password=False))
    try:
        with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
            connection.execute(text(f'CREATE DATABASE "{name}"'))
    finally:
        admin.dispose()

    rendered = target.render_as_string(hide_password=False)
    engine = create_db_engine(rendered)
    try:
        with engine.begin() as connection:
            # Migration 0001 installs PostGIS WITH SCHEMA extensions; on Supabase that schema
            # only exists in the postgres database.
            connection.execute(text("CREATE SCHEMA IF NOT EXISTS extensions"))
        _migrate(rendered)
        with Session(engine) as session, session.begin():
            return run_seed(session, seed)
    finally:
        engine.dispose()


def _migrate(url: str) -> None:
    # A subprocess, because env.py reads DATABASE_URL and its fileConfig disables every
    # logger already created in this process.
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), "upgrade", "head"],
        env={**os.environ, "DATABASE_URL": url},
        check=True,
    )
