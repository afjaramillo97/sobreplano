"""Integration tests for SqlScrapeRunRepository."""

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from sobreplano.domain.catalog import Developer
from sobreplano.domain.scraping import (
    ExtractedProject,
    ExtractedUnitType,
    ExtractionResult,
    ScrapedPage,
    ScrapeRunStatus,
)
from sobreplano.infrastructure.db.models import PageExtractionRow, ScrapedPageRow, ScrapeRunRow
from sobreplano.infrastructure.db.scrape_run_repository import SqlScrapeRunRepository

pytestmark = pytest.mark.integration

SHA = "a" * 64
TEXT_SHA = "e" * 64
FETCHED_AT = datetime(2026, 10, 30, 15, 0, tzinfo=UTC)
RESULT = ExtractionResult(
    prompt_version="6682e7fa8220",
    model="openai:gpt-6-luna",
    input_tokens=1200,
    output_tokens=150,
    project=ExtractedProject(
        name="Réflex Living",
        neighborhood="Pan de Azúcar",
        unit_types=(
            ExtractedUnitType(
                name="Tipo 1",
                price_cop=426_706_000,
                total_area_m2=Decimal("55.0"),
                private_area_m2=Decimal("49.36"),
                bedrooms=2,
                bathrooms=None,
            ),
        ),
    ),
)


@pytest.fixture
def runs(session: Session) -> SqlScrapeRunRepository:
    return SqlScrapeRunRepository(session)


def page(url: str = "https://londonogomez.com/proyectos-vivienda/antioquia/x/y") -> ScrapedPage:
    return ScrapedPage(
        url=url,
        http_status=200,
        content_sha256=SHA,
        text_sha256=TEXT_SHA,
        storage_key=f"londono-gomez/2026-10-30/{SHA}.html",
        fetched_at=FETCHED_AT,
    )


def test_start_and_finish_round_trip(
    runs: SqlScrapeRunRepository, session: Session, developer: Developer
) -> None:
    run = runs.start(developer.id, date(2026, 10, 30))
    runs.finish(
        replace(
            run,
            status=ScrapeRunStatus.SUCCEEDED,
            finished_at=FETCHED_AT,
            pages_fetched=20,
            pages_failed=2,
            observations_recorded=45,
        )
    )
    row = session.scalars(select(ScrapeRunRow).where(ScrapeRunRow.id == run.id)).one()
    session.refresh(row)
    assert row.status is ScrapeRunStatus.SUCCEEDED
    assert (row.pages_fetched, row.pages_failed, row.observations_recorded) == (20, 2, 45)
    assert row.finished_at == FETCHED_AT
    assert row.error is None


def test_record_page_stores_the_canonical_url_and_both_hashes(
    runs: SqlScrapeRunRepository, session: Session, developer: Developer
) -> None:
    run = runs.start(developer.id, date(2026, 10, 30))
    runs.record_page(run.id, page())
    row = session.scalars(
        select(ScrapedPageRow).where(ScrapedPageRow.scrape_run_id == run.id)
    ).one()
    assert row.url == page().url
    assert (row.content_sha256, row.text_sha256) == (SHA, TEXT_SHA)


def test_same_url_twice_in_a_run_is_rejected(
    runs: SqlScrapeRunRepository, developer: Developer
) -> None:
    run = runs.start(developer.id, date(2026, 10, 30))
    runs.record_page(run.id, page())
    with pytest.raises(IntegrityError, match="uq_scraped_pages_scrape_run_id_url"):
        runs.record_page(run.id, page())


def test_extraction_round_trip(runs: SqlScrapeRunRepository) -> None:
    sha = "b" * 64
    assert runs.find_extraction(sha, RESULT.model, RESULT.prompt_version) is None
    runs.save_extraction(sha, RESULT)
    assert runs.find_extraction(sha, RESULT.model, RESULT.prompt_version) == RESULT


def test_extraction_is_keyed_by_model_too(runs: SqlScrapeRunRepository) -> None:
    sha = "c" * 64
    runs.save_extraction(sha, RESULT)
    assert runs.find_extraction(sha, "qwen:qwen3.7-flash", RESULT.prompt_version) is None


def test_extraction_is_keyed_by_prompt_version_too(runs: SqlScrapeRunRepository) -> None:
    sha = "9" * 64
    runs.save_extraction(sha, RESULT)
    assert runs.find_extraction(sha, RESULT.model, "000000000000") is None
    # A new prompt's extraction of the same text is stored next to the old one.
    newer = replace(RESULT, prompt_version="000000000000", input_tokens=7)
    runs.save_extraction(sha, newer)
    assert runs.find_extraction(sha, RESULT.model, "000000000000") == newer
    assert runs.find_extraction(sha, RESULT.model, RESULT.prompt_version) == RESULT


def test_same_text_model_and_prompt_twice_hits_the_unique(session: Session) -> None:
    # Checks the unique on the migrated schema, under its name from migration 0008.
    def row() -> PageExtractionRow:
        return PageExtractionRow(
            id=uuid4(),
            text_sha256="f" * 64,
            model=RESULT.model,
            prompt_version=RESULT.prompt_version,
            input_tokens=1,
            output_tokens=1,
            payload={},
        )

    session.add(row())
    session.flush()
    session.add(row())
    with pytest.raises(
        IntegrityError, match="uq_page_extractions_text_sha256_model_prompt_version"
    ):
        session.flush()


def test_saving_the_same_extraction_twice_keeps_the_first(runs: SqlScrapeRunRepository) -> None:
    sha = "d" * 64
    runs.save_extraction(sha, RESULT)
    runs.save_extraction(sha, replace(RESULT, input_tokens=9999))
    stored = runs.find_extraction(sha, RESULT.model, RESULT.prompt_version)
    assert stored is not None
    assert stored.input_tokens == 1200


def test_has_succeeded_only_counts_succeeded_runs_of_that_day(
    runs: SqlScrapeRunRepository, developer: Developer
) -> None:
    day = date(2026, 10, 30)
    failed = runs.start(developer.id, day)
    runs.finish(replace(failed, status=ScrapeRunStatus.FAILED, finished_at=FETCHED_AT))
    assert not runs.has_succeeded(developer.id, day)

    succeeded = runs.start(developer.id, day)
    runs.finish(replace(succeeded, status=ScrapeRunStatus.SUCCEEDED, finished_at=FETCHED_AT))
    assert runs.has_succeeded(developer.id, day)
    assert not runs.has_succeeded(developer.id, date(2026, 10, 31))


def test_skipped_status_is_accepted_by_the_check(
    runs: SqlScrapeRunRepository, session: Session, developer: Developer
) -> None:
    run = runs.start(developer.id, date(2026, 10, 30))
    runs.finish(replace(run, status=ScrapeRunStatus.SKIPPED, error="already succeeded"))
    session.flush()
    row = session.get_one(ScrapeRunRow, run.id)
    session.refresh(row)
    assert row.status is ScrapeRunStatus.SKIPPED


def test_lock_is_exclusive_across_transactions_and_released_at_the_end(engine: Engine) -> None:
    developer_id = uuid4()  # the lock needs no row, only the key
    with Session(engine) as first, Session(engine) as second:
        assert SqlScrapeRunRepository(first).try_lock(developer_id)
        # Same transaction again: Postgres advisory locks are reentrant.
        assert SqlScrapeRunRepository(first).try_lock(developer_id)
        assert not SqlScrapeRunRepository(second).try_lock(developer_id)
        assert SqlScrapeRunRepository(second).try_lock(uuid4())
        first.rollback()
        second.rollback()
        assert SqlScrapeRunRepository(second).try_lock(developer_id)
        second.rollback()
