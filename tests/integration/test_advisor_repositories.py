"""Integration tests for the advisor's usage log, conversations and checkpointer tables."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from sobreplano.domain.advisor import LlmCall
from sobreplano.infrastructure.db.advisor_thread_repository import SqlAdvisorThreadRepository
from sobreplano.infrastructure.db.llm_usage_repository import SqlLlmUsageRepository
from sobreplano.infrastructure.db.models import LlmUsageRow

pytestmark = pytest.mark.integration

# A day far in the past, so rows from real local runs never add to the sums.
DAY = date(2020, 3, 10)


def call(cost: str | None = "0.001000") -> LlmCall:
    return LlmCall(
        model="openai:gpt-6-luna",
        input_tokens=1500,
        output_tokens=200,
        cost_usd=Decimal(cost) if cost is not None else None,
    )


@pytest.fixture
def usage(session: Session) -> SqlLlmUsageRepository:
    return SqlLlmUsageRepository(session)


@pytest.fixture
def threads(session: Session) -> SqlAdvisorThreadRepository:
    return SqlAdvisorThreadRepository(session)


def add_at(session: Session, usage: SqlLlmUsageRepository, at: datetime, cost: str | None) -> None:
    usage.add("advisor", call(cost), thread_id=None)
    # now() is fixed for the test's transaction and each earlier row was already moved,
    # so the row just written is the only one at now().
    session.execute(
        text("UPDATE llm_usage SET created_at = :at WHERE created_at = now()"), {"at": at}
    )


def test_add_stores_model_tokens_cost_and_thread(
    session: Session, usage: SqlLlmUsageRepository
) -> None:
    thread_id = uuid4()
    usage.add("advisor", call(), thread_id=thread_id)
    row = session.query(LlmUsageRow).filter_by(thread_id=thread_id).one()
    assert (row.feature, row.model, row.input_tokens, row.output_tokens, row.cost_usd) == (
        "advisor",
        "openai:gpt-6-luna",
        1500,
        200,
        Decimal("0.001000"),
    )


def test_unknown_feature_is_rejected(session: Session, usage: SqlLlmUsageRepository) -> None:
    with pytest.raises(IntegrityError, match="ck_llm_usage_feature_known"):
        usage.add("scraper", call(), thread_id=None)


def test_cost_on_sums_the_bogota_day(session: Session, usage: SqlLlmUsageRepository) -> None:
    # Bogotá is UTC-5: 04:59 UTC on the 11th is still the 10th there; 05:00 UTC is the 11th.
    add_at(session, usage, datetime(2020, 3, 10, 5, 0, tzinfo=UTC), "0.010000")
    add_at(session, usage, datetime(2020, 3, 11, 4, 59, tzinfo=UTC), "0.002500")
    add_at(session, usage, datetime(2020, 3, 11, 4, 59, tzinfo=UTC), None)
    add_at(session, usage, datetime(2020, 3, 11, 5, 0, tzinfo=UTC), "1.000000")
    add_at(session, usage, datetime(2020, 3, 10, 4, 59, tzinfo=UTC), "1.000000")

    assert usage.cost_on("advisor", DAY) == Decimal("0.012500")


def test_cost_on_a_day_without_calls_is_zero(usage: SqlLlmUsageRepository) -> None:
    assert usage.cost_on("advisor", date(2019, 1, 1)) == Decimal(0)


def test_new_thread_has_no_turns(threads: SqlAdvisorThreadRepository) -> None:
    assert threads.get_turns(threads.create()) == 0


def test_unknown_thread_has_no_turns(threads: SqlAdvisorThreadRepository) -> None:
    assert threads.get_turns(uuid4()) is None


def test_record_turn_counts_messages(threads: SqlAdvisorThreadRepository) -> None:
    thread_id = threads.create()
    threads.record_turn(thread_id)
    threads.record_turn(thread_id)
    assert threads.get_turns(thread_id) == 2


def set_last_message_at(session: Session, thread_id: UUID, at: datetime) -> None:
    session.execute(
        text("UPDATE advisor_threads SET last_message_at = :at WHERE id = :id"),
        {"at": at, "id": thread_id},
    )


def test_list_inactive_since_returns_only_old_threads(
    session: Session, threads: SqlAdvisorThreadRepository
) -> None:
    old, recent = threads.create(), threads.create()
    now = datetime.now(UTC)
    set_last_message_at(session, old, now - timedelta(days=8))
    set_last_message_at(session, recent, now - timedelta(days=6))

    inactive = threads.list_inactive_since(now - timedelta(days=7))

    assert old in inactive
    assert recent not in inactive


def test_record_turn_refreshes_last_activity(
    session: Session, threads: SqlAdvisorThreadRepository
) -> None:
    thread_id = threads.create()
    now = datetime.now(UTC)
    set_last_message_at(session, thread_id, now - timedelta(days=30))
    threads.record_turn(thread_id)
    assert thread_id not in threads.list_inactive_since(now - timedelta(days=7))


def test_delete_removes_the_thread(threads: SqlAdvisorThreadRepository) -> None:
    thread_id = threads.create()
    threads.delete(thread_id)
    assert threads.get_turns(thread_id) is None


def test_checkpointer_sees_its_migrations_applied(session: Session) -> None:
    versions = session.scalars(text("SELECT v FROM checkpoint_migrations ORDER BY v")).all()
    assert versions == list(range(10))


def test_checkpoint_writes_has_the_last_migration_column(session: Session) -> None:
    columns = session.scalars(
        text(
            "SELECT column_name FROM information_schema.columns"
            " WHERE table_schema = 'public' AND table_name = 'checkpoint_writes'"
        )
    ).all()
    assert "task_path" in columns
