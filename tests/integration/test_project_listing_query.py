"""Integration tests for SqlProjectListingQuery."""

from datetime import date

import pytest
from factories import (
    MUNICIPALITY,
    OTHER_MUNICIPALITY,
    add_price,
    add_project,
    add_unit_type,
)
from sqlalchemy.orm import Session

from sobreplano.domain.catalog import Developer, GeoPoint
from sobreplano.domain.listings import AreaBasis
from sobreplano.infrastructure.db.catalog_repository import SqlCatalogRepository
from sobreplano.infrastructure.db.price_observation_repository import (
    SqlPriceObservationRepository,
)
from sobreplano.infrastructure.db.project_listing_query import SqlProjectListingQuery

pytestmark = pytest.mark.integration


@pytest.fixture
def query(session: Session) -> SqlProjectListingQuery:
    return SqlProjectListingQuery(session)


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
