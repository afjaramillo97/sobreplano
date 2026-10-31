"""Integration tests for SqlScrapeRunRepository."""

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
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
from sobreplano.infrastructure.db.models import ScrapedPageRow, ScrapeRunRow
from sobreplano.infrastructure.db.scrape_run_repository import SqlScrapeRunRepository

pytestmark = pytest.mark.integration

SHA = "a" * 64
FETCHED_AT = datetime(2026, 10, 30, 15, 0, tzinfo=UTC)
RESULT = ExtractionResult(
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


def test_record_page_stores_the_canonical_url(
    runs: SqlScrapeRunRepository, session: Session, developer: Developer
) -> None:
    run = runs.start(developer.id, date(2026, 10, 30))
    runs.record_page(run.id, page())
    row = session.scalars(
        select(ScrapedPageRow).where(ScrapedPageRow.scrape_run_id == run.id)
    ).one()
    assert row.url == page().url
    assert row.content_sha256 == SHA


def test_same_url_twice_in_a_run_is_rejected(
    runs: SqlScrapeRunRepository, developer: Developer
) -> None:
    run = runs.start(developer.id, date(2026, 10, 30))
    runs.record_page(run.id, page())
    with pytest.raises(IntegrityError, match="uq_scraped_pages_scrape_run_id_url"):
        runs.record_page(run.id, page())


def test_extraction_round_trip(runs: SqlScrapeRunRepository) -> None:
    sha = "b" * 64
    assert runs.find_extraction(sha, RESULT.model) is None
    runs.save_extraction(sha, RESULT)
    assert runs.find_extraction(sha, RESULT.model) == RESULT


def test_extraction_is_keyed_by_model_too(runs: SqlScrapeRunRepository) -> None:
    sha = "c" * 64
    runs.save_extraction(sha, RESULT)
    assert runs.find_extraction(sha, "qwen:qwen3.7-flash") is None


def test_saving_the_same_extraction_twice_keeps_the_first(runs: SqlScrapeRunRepository) -> None:
    sha = "d" * 64
    runs.save_extraction(sha, RESULT)
    runs.save_extraction(sha, replace(RESULT, input_tokens=9999))
    stored = runs.find_extraction(sha, RESULT.model)
    assert stored is not None
    assert stored.input_tokens == 1200
