"""Guards that migration 0007 still matches the checkpointer library's own schema."""

import importlib.util
from pathlib import Path
from typing import Any

from langgraph.checkpoint.postgres import PostgresSaver

MIGRATION = Path(__file__).parents[3] / "migrations" / "versions" / "0007_advisor.py"


def load_migration() -> Any:
    spec = importlib.util.spec_from_file_location("migration_0007", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_library_has_the_ten_migrations_that_0007_applies() -> None:
    # A new library version with more migrations needs a new Alembic migration (SPEC 08).
    assert len(PostgresSaver.MIGRATIONS) == 10


def test_0007_copies_the_library_sql_without_concurrently() -> None:
    expected = [sql.replace("CONCURRENTLY ", "") for sql in PostgresSaver.MIGRATIONS]
    assert list(load_migration().CHECKPOINT_MIGRATIONS) == expected
