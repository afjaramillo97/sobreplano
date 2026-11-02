"""Engine options for the Supabase transaction pooler and for Lambda."""

from sqlalchemy.pool import NullPool

from sobreplano.infrastructure.db.engine import create_db_engine, engine_options

POOLER_TRANSACTION = (
    "postgresql+psycopg://postgres.ref:pw@aws-0-us-east-1.pooler.supabase.com:6543/postgres"
)
POOLER_SESSION = (
    "postgresql+psycopg://postgres.ref:pw@aws-0-us-east-1.pooler.supabase.com:5432/postgres"
)
LOCAL = "postgresql+psycopg://postgres:postgres@127.0.0.1:54322/postgres"


def test_transaction_pooler_turns_prepared_statements_off() -> None:
    assert engine_options(POOLER_TRANSACTION) == {"connect_args": {"prepare_threshold": None}}


def test_session_pooler_and_local_keep_the_defaults() -> None:
    assert engine_options(POOLER_SESSION) == {}
    assert engine_options(LOCAL) == {}


def test_null_pool_is_opt_in() -> None:
    assert engine_options(LOCAL, null_pool=True) == {"poolclass": NullPool}
    assert engine_options(POOLER_TRANSACTION, null_pool=True) == {
        "connect_args": {"prepare_threshold": None},
        "poolclass": NullPool,
    }


def test_create_db_engine_applies_the_options() -> None:
    # create_engine opens no connection, so this needs no database.
    engine = create_db_engine(POOLER_TRANSACTION, null_pool=True)
    try:
        assert isinstance(engine.pool, NullPool)
    finally:
        engine.dispose()
