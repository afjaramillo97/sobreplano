"""Integration tests for SqlProjectListingQuery."""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from sobreplano.domain.catalog import Developer, GeoPoint, Municipality, Project, UnitType
from sobreplano.domain.listings import AreaBasis
from sobreplano.domain.pricing import ObservationSource, PriceObservation
from sobreplano.infrastructure.db.catalog_repository import SqlCatalogRepository
from sobreplano.infrastructure.db.price_observation_repository import (
    SqlPriceObservationRepository,
)
from sobreplano.infrastructure.db.project_listing_query import SqlProjectListingQuery

pytestmark = pytest.mark.integration

# The seed only has Envigado projects, so these two municipalities start empty in every test.
MUNICIPALITY = Municipality.ITAGUI
OTHER_MUNICIPALITY = Municipality.CALDAS


@pytest.fixture
def query(session: Session) -> SqlProjectListingQuery:
    return SqlProjectListingQuery(session)


def add_project(
    catalog: SqlCatalogRepository,
    developer: Developer,
    name: str,
    municipality: Municipality = MUNICIPALITY,
) -> Project:
    project = Project(
        id=uuid4(),
        developer_id=developer.id,
        name=name,
        slug=f"proj-{uuid4().hex[:8]}",
        municipality=municipality,
        neighborhood=None,
        location=GeoPoint(lat=6.1735, lon=-75.5925),
        source_url="https://example.com/proyecto",
    )
    catalog.add_project(project)
    return project


def add_unit_type(
    catalog: SqlCatalogRepository,
    project: Project,
    name: str,
    private_area_m2: str | None = "50.00",
    built_area_m2: str | None = None,
) -> UnitType:
    unit_type = UnitType(
        id=uuid4(),
        project_id=project.id,
        name=name,
        private_area_m2=Decimal(private_area_m2) if private_area_m2 else None,
        built_area_m2=Decimal(built_area_m2) if built_area_m2 else None,
        bedrooms=2,
        bathrooms=2,
    )
    catalog.add_unit_type(unit_type)
    return unit_type


def add_price(
    observations: SqlPriceObservationRepository, unit_type: UnitType, day: int, price_cop: int
) -> None:
    observations.add(
        PriceObservation(
            id=uuid4(),
            unit_type_id=unit_type.id,
            price_cop=price_cop,
            observed_at=datetime(2026, 10, day, 15, 0, tzinfo=UTC),
            observed_on=date(2026, 10, day),
            source=ObservationSource.MANUAL,
            source_url="https://example.com/proyecto",
        )
    )


def test_latest_price_is_the_most_recent_day(
    query: SqlProjectListingQuery,
    catalog: SqlCatalogRepository,
    observations: SqlPriceObservationRepository,
    developer: Developer,
) -> None:
    project = add_project(catalog, developer, "Proyecto A")
    unit_type = add_unit_type(catalog, project, "Tipo 01", private_area_m2="50.00")
    add_price(observations, unit_type, 27, 400_000_000)
    add_price(observations, unit_type, 28, 450_000_000)

    page = query.list_projects(municipality=MUNICIPALITY, limit=50, offset=0)

    [listing] = page.items
    assert listing.slug == project.slug
    assert listing.developer_slug == developer.slug
    assert listing.location == GeoPoint(lat=6.1735, lon=-75.5925)
    [unit] = listing.unit_types
    assert unit.latest_price is not None
    assert unit.latest_price.price_cop == 450_000_000
    assert unit.latest_price.observed_on == date(2026, 10, 28)
    assert unit.price_per_m2_cop == 9_000_000
    assert unit.area_basis == AreaBasis.PRIVATE


def test_unit_type_without_observations_has_no_price(
    query: SqlProjectListingQuery, catalog: SqlCatalogRepository, developer: Developer
) -> None:
    project = add_project(catalog, developer, "Proyecto A")
    add_unit_type(catalog, project, "Tipo 01")

    [listing] = query.list_projects(municipality=MUNICIPALITY, limit=50, offset=0).items

    [unit] = listing.unit_types
    assert unit.latest_price is None
    assert unit.price_per_m2_cop is None


def test_unit_types_are_ordered_by_name(
    query: SqlProjectListingQuery, catalog: SqlCatalogRepository, developer: Developer
) -> None:
    project = add_project(catalog, developer, "Proyecto A")
    add_unit_type(catalog, project, "Tipo 02")
    add_unit_type(catalog, project, "Tipo 01", private_area_m2=None, built_area_m2="60.00")

    [listing] = query.list_projects(municipality=MUNICIPALITY, limit=50, offset=0).items

    assert [unit.name for unit in listing.unit_types] == ["Tipo 01", "Tipo 02"]
    assert listing.unit_types[0].area_basis == AreaBasis.BUILT


def test_municipality_filter_applies_to_items_and_total(
    query: SqlProjectListingQuery, catalog: SqlCatalogRepository, developer: Developer
) -> None:
    add_project(catalog, developer, "Proyecto A")
    add_project(catalog, developer, "Proyecto B")
    add_project(catalog, developer, "Proyecto C", municipality=OTHER_MUNICIPALITY)

    page = query.list_projects(municipality=MUNICIPALITY, limit=50, offset=0)
    other = query.list_projects(municipality=OTHER_MUNICIPALITY, limit=50, offset=0)

    assert page.total == 2
    assert [item.name for item in page.items] == ["Proyecto A", "Proyecto B"]
    assert other.total == 1


def test_without_filter_every_municipality_is_counted(
    query: SqlProjectListingQuery, catalog: SqlCatalogRepository, developer: Developer
) -> None:
    before = query.list_projects(municipality=None, limit=1, offset=0).total
    add_project(catalog, developer, "Proyecto A")
    add_project(catalog, developer, "Proyecto C", municipality=OTHER_MUNICIPALITY)

    assert query.list_projects(municipality=None, limit=1, offset=0).total == before + 2


def test_pagination_keeps_total_and_order(
    query: SqlProjectListingQuery, catalog: SqlCatalogRepository, developer: Developer
) -> None:
    for name in ("Proyecto C", "Proyecto A", "Proyecto B"):
        add_project(catalog, developer, name)

    first = query.list_projects(municipality=MUNICIPALITY, limit=2, offset=0)
    second = query.list_projects(municipality=MUNICIPALITY, limit=2, offset=2)
    beyond = query.list_projects(municipality=MUNICIPALITY, limit=2, offset=10)

    assert [item.name for item in first.items] == ["Proyecto A", "Proyecto B"]
    assert [item.name for item in second.items] == ["Proyecto C"]
    assert first.total == second.total == beyond.total == 3
    assert beyond.items == []
