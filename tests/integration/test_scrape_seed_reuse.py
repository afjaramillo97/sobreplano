"""Integration test: a scraped page reuses a hand-loaded seed project and its unit types."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sobreplano.application.record_price_observation import RecordPriceObservation
from sobreplano.application.scrape_developer import ScrapeDeveloper
from sobreplano.domain.catalog import Developer, GeoPoint, Municipality, Project, UnitType
from sobreplano.domain.scraping import (
    ExtractedProject,
    ExtractedUnitType,
    ExtractionResult,
    FetchedPage,
    ParsedProjectPage,
)
from sobreplano.infrastructure.db.catalog_repository import SqlCatalogRepository
from sobreplano.infrastructure.db.models import PriceObservationRow, ProjectRow, UnitTypeRow
from sobreplano.infrastructure.db.price_observation_repository import (
    SqlPriceObservationRepository,
)
from sobreplano.infrastructure.db.scrape_run_repository import SqlScrapeRunRepository

pytestmark = pytest.mark.integration

LISTING = "https://example.com/proyectos"
NODE = "https://example.com/proyecto/262"
NOW = datetime(2026, 11, 2, 15, 0, tzinfo=UTC)


class OnePageSite:
    """A site whose one project page has a seed project's URL but another slug."""

    name = "Constructora de prueba"
    website_url = "https://example.com"
    listing_url = LISTING

    def __init__(self, developer: Developer, canonical_url: str) -> None:
        self.slug = developer.slug
        self.canonical_url = canonical_url

    def project_urls(self, listing_html: str) -> list[str]:
        return [NODE]

    def parse_project(self, page: FetchedPage) -> ParsedProjectPage:
        return ParsedProjectPage(
            canonical_url=self.canonical_url,
            municipality=Municipality.ENVIGADO,
            slug="axis",
            location=GeoPoint(lat=6.1719777, lon=-75.5941694),
            text="Planta Apartamento 60.01 m2 Área Total Desde $ 710,200,000",
        )


class Fetcher:
    def fetch(self, url: str) -> FetchedPage:
        return FetchedPage(url=url, status=200, html=f"<html>{url}</html>", fetched_at=NOW)


class Store:
    def save(self, developer_slug: str, page: FetchedPage) -> str:
        return f"{developer_slug}/{page.url}"


class Extractor:
    model = "openai:gpt-6-luna"

    def extract(self, page_text: str) -> ExtractionResult:
        unit = ExtractedUnitType(
            name="Planta Apartamento 60.01 m2",
            price_cop=710_200_000,
            total_area_m2=Decimal("60.01"),
            private_area_m2=Decimal("54.06"),
            bedrooms=1,
            bathrooms=1,
        )
        project = ExtractedProject(name="Axis", neighborhood=None, unit_types=(unit,))
        return ExtractionResult(model=self.model, input_tokens=1, output_tokens=1, project=project)


def test_page_reuses_the_seed_project_and_its_unit_type_by_area(
    session: Session, catalog: SqlCatalogRepository, developer: Developer
) -> None:
    url = f"https://example.com/proyecto/1/envigado/262/axis-{uuid4().hex[:8]}"
    seeded = Project(
        id=uuid4(),
        developer_id=developer.id,
        name="AXIS - Ciudad Peldar",
        slug=f"axis-ciudad-peldar-{uuid4().hex[:8]}",
        municipality=Municipality.ENVIGADO,
        neighborhood="Las Vegas",
        location=GeoPoint(lat=6.1735, lon=-75.5925),
        source_url=url,
    )
    catalog.add_project(seeded)
    tipo_04 = UnitType(
        id=uuid4(),
        project_id=seeded.id,
        name="Tipo 04",
        private_area_m2=Decimal("54.06"),
        built_area_m2=Decimal("60.01"),
        bedrooms=1,
        bathrooms=1,
    )
    catalog.add_unit_type(tipo_04)

    report = ScrapeDeveloper(
        site=OnePageSite(developer, url),
        fetcher=Fetcher(),
        store=Store(),
        extractor=Extractor(),
        runs=SqlScrapeRunRepository(session),
        catalog=catalog,
        record=RecordPriceObservation(SqlPriceObservationRepository(session)),
        now=lambda: NOW,
    ).execute()

    assert (report.projects_added, report.unit_types_added, report.observations_recorded) == (
        0,
        0,
        1,
    )
    assert session.scalar(select(func.count()).where(ProjectRow.source_url == url)) == 1
    names = session.scalars(
        select(UnitTypeRow.name).where(UnitTypeRow.project_id == seeded.id)
    ).all()
    assert names == ["Tipo 04"]
    observed = session.scalars(
        select(PriceObservationRow.price_cop).where(PriceObservationRow.unit_type_id == tipo_04.id)
    ).all()
    assert observed == [710_200_000]
