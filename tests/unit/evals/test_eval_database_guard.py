"""Unit tests for the guard that keeps the fictitious catalog off any non-local database."""

import pytest

from sobreplano.evals.advisor import database
from sobreplano.evals.advisor.database import UnsafeEvalDatabaseError, check_local, prepare


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://postgres:x@db.abcdefgh.supabase.co:5432/sobreplano_evals",
        "postgresql+psycopg://postgres:x@aws-0-us-east-1.pooler.supabase.com:6543/evals",
        "postgresql+psycopg://postgres:x@10.0.0.5:5432/sobreplano_evals",
    ],
)
def test_remote_hosts_are_refused(url: str) -> None:
    with pytest.raises(UnsafeEvalDatabaseError, match="host"):
        check_local(url)


@pytest.mark.parametrize(
    "name", ["postgres", "template0", "template1", "", 'evals"; drop', "Evals"]
)
def test_protected_or_odd_database_names_are_refused(name: str) -> None:
    with pytest.raises(UnsafeEvalDatabaseError, match="refusing"):
        check_local(f"postgresql+psycopg://postgres:postgres@127.0.0.1:54322/{name}")


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost"])
def test_local_disposable_database_is_accepted(host: str) -> None:
    assert check_local(f"postgresql+psycopg://p:p@{host}:54322/sobreplano_evals").database == (
        "sobreplano_evals"
    )


def test_prepare_on_a_remote_host_touches_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("prepare connected to a database")

    monkeypatch.setattr(database, "create_db_engine", fail)
    with pytest.raises(UnsafeEvalDatabaseError):
        prepare("postgresql+psycopg://postgres:x@db.example.supabase.co:5432/sobreplano_evals")


def test_default_url_is_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EVAL_DATABASE_URL", raising=False)
    assert check_local(database.eval_database_url()).database == "sobreplano_evals"
