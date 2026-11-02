"""Integration test of the scrape CLI's transaction: the real parser and Postgres, no network."""

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from sobreplano.domain.catalog import Developer
from sobreplano.domain.scraping import (
    ExtractedProject,
    ExtractedUnitType,
    ExtractionResult,
    FetchedPage,
    ScrapeRunStatus,
)
from sobreplano.infrastructure.db.catalog_repository import SqlCatalogRepository
from sobreplano.infrastructure.db.models import (
    DeveloperRow,
    PageExtractionRow,
    PriceObservationRow,
    ProjectRow,
    ScrapeRunRow,
)
from sobreplano.infrastructure.db.scrape_run_repository import SqlScrapeRunRepository
from sobreplano.infrastructure.scraping.file_store import FileRawPageStore
from sobreplano.infrastructure.scraping.londono_gomez import BASE_URL, LondonoGomezSite
from sobreplano.interface.composition import scrape

pytestmark = pytest.mark.integration


class TestSite(LondonoGomezSite):
    """The real parser under a random developer slug, so it never meets real scraped data."""

    __test__ = False  # not a pytest test class

    def __init__(self) -> None:
        self.slug = f"test-{uuid4().hex[:8]}"


class SyntheticFetcher:
    """Serves a hand-written listing with one card and its project page."""

    def __init__(self, project_slug: str) -> None:
        self.project_slug = project_slug
        self.requested: list[str] = []

    def fetch(self, url: str) -> FetchedPage:
        self.requested.append(url)
        if url.endswith("/proyectos-vivienda"):
            html = """
            <div class="view-busqueda-proyectos"><div class="views-row">
              <div class="views-field-title">Primavela</div>
              <div class="views-field-field-tipo-de-proyecto">Vivienda</div>
              <div class="views-field-nothing">Bello</div>
              <a href="/node/1">Más información</a>
            </div></div>"""
            return self._page(url, html)
        canonical = f"{BASE_URL}/proyectos-vivienda/antioquia/bello/{self.project_slug}"
        html = f"""<html><head><link rel="canonical" href="{canonical}"></head><body>
            <h4>TIPO B</h4><p>Desde $506.100.000 *</p>
            <a href="https://www.google.com/maps/dir//6.3296009,-75.5595542/@x">Mapa</a>
            </body></html>"""
        return self._page(canonical, html)

    def _page(self, url: str, html: str) -> FetchedPage:
        return FetchedPage(
            url=url, status=200, html=html, fetched_at=datetime(2026, 10, 30, 15, tzinfo=UTC)
        )


class FixedExtractor:
    model = "openai:gpt-6-luna"

    def extract(self, page_text: str) -> ExtractionResult:
        unit = ExtractedUnitType(
            name="TIPO B",
            price_cop=506_100_000,
            total_area_m2=Decimal("55.58"),
            private_area_m2=None,
            bedrooms=None,
            bathrooms=None,
        )
        return ExtractionResult(
            model=self.model,
            input_tokens=900,
            output_tokens=80,
            project=ExtractedProject(name="Primavela", neighborhood=None, unit_types=(unit,)),
        )


@pytest.fixture
def session_factory(engine: Engine) -> Iterator[sessionmaker[Session]]:
    """Sessions whose commits land in a savepoint of an outer transaction that is rolled back."""
    with engine.connect() as connection:
        transaction = connection.begin()
        yield sessionmaker(bind=connection, join_transaction_mode="create_savepoint")
        transaction.rollback()


def count(session_factory: sessionmaker[Session], table: type[object], **where: object) -> int:
    with session_factory() as session:
        statement = select(func.count()).select_from(table).filter_by(**where)
        return session.scalar(statement) or 0


def run(
    session_factory: sessionmaker[Session],
    tmp_path: Path,
    site: TestSite,
    *,
    dry_run: bool,
    force: bool = False,
    fetcher: SyntheticFetcher | None = None,
) -> ScrapeRunStatus:
    # Each project needs a unique slug; real data may already hold "primavela".
    fetcher = fetcher or SyntheticFetcher(project_slug=site.slug)
    report = scrape(
        session_factory,
        site=site,
        fetcher=fetcher,
        store=FileRawPageStore(tmp_path),
        extractor=FixedExtractor(),
        limit=None,
        dry_run=dry_run,
        force=force,
    )
    return report.status


def test_dry_run_leaves_no_rows(session_factory: sessionmaker[Session], tmp_path: Path) -> None:
    site = TestSite()
    before = count(session_factory, PriceObservationRow)

    assert run(session_factory, tmp_path, site, dry_run=True) is ScrapeRunStatus.SUCCEEDED

    assert count(session_factory, PriceObservationRow) == before
    assert count(session_factory, ProjectRow, slug=site.slug) == 0
    # The raw HTML is kept: a dry run still downloads.
    assert len(list(tmp_path.rglob("*.html"))) == 1


def test_real_run_commits_project_price_run_and_extraction(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    site = TestSite()
    before = count(session_factory, PriceObservationRow)

    assert run(session_factory, tmp_path, site, dry_run=False) is ScrapeRunStatus.SUCCEEDED

    assert count(session_factory, PriceObservationRow) == before + 1
    assert count(session_factory, ProjectRow, slug=site.slug) == 1
    assert count(session_factory, ScrapeRunRow, status=ScrapeRunStatus.SUCCEEDED) >= 1
    assert count(session_factory, PageExtractionRow, model="openai:gpt-6-luna") >= 1


def test_forced_second_run_same_day_adds_no_observation(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    site = TestSite()
    run(session_factory, tmp_path, site, dry_run=False)
    after_first = count(session_factory, PriceObservationRow)

    status = run(session_factory, tmp_path, site, dry_run=False, force=True)

    assert status is ScrapeRunStatus.SUCCEEDED
    assert count(session_factory, PriceObservationRow) == after_first


def test_second_run_same_day_is_skipped_without_requests(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    site = TestSite()
    run(session_factory, tmp_path, site, dry_run=False)
    fetcher = SyntheticFetcher(project_slug=site.slug)

    status = run(session_factory, tmp_path, site, dry_run=False, fetcher=fetcher)

    assert status is ScrapeRunStatus.SKIPPED
    assert fetcher.requested == []
    assert count(session_factory, ScrapeRunRow, status=ScrapeRunStatus.SKIPPED) >= 1


def test_concurrent_run_is_skipped_without_requests(engine: Engine, tmp_path: Path) -> None:
    """A second connection runs while the first holds the developer's lock, as two Lambdas would."""
    site = TestSite()
    developer = Developer(id=uuid4(), name=site.name, slug=site.slug, website_url=site.website_url)
    # Both connections must see the developer, so it is committed and deleted at the end.
    with Session(engine) as setup:
        SqlCatalogRepository(setup).add_developer(developer)
        setup.commit()
    try:
        with Session(engine) as first_run, engine.connect() as connection:
            assert SqlScrapeRunRepository(first_run).try_lock(developer.id)
            transaction = connection.begin()
            fetcher = SyntheticFetcher(project_slug=site.slug)
            second = sessionmaker(bind=connection, join_transaction_mode="create_savepoint")

            status = run(second, tmp_path, site, dry_run=False, fetcher=fetcher)

            assert status is ScrapeRunStatus.SKIPPED
            assert fetcher.requested == []
            transaction.rollback()
            first_run.rollback()
    finally:
        with Session(engine) as cleanup:
            cleanup.execute(delete(DeveloperRow).where(DeveloperRow.id == developer.id))
            cleanup.commit()
