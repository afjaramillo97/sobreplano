"""Integration tests for SqlProjectListingQuery."""

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from factories import (
    MUNICIPALITY,
    OTHER_MUNICIPALITY,
    add_price,
    add_project,
    add_unit_type,
)
from sqlalchemy.orm import Session

from sobreplano.domain.catalog import Developer, GeoPoint, Municipality
from sobreplano.domain.listings import (
    AreaBasis,
    ProjectFilters,
    ProjectPage,
    ProjectSort,
)
from sobreplano.domain.pricing import ObservationSource
from sobreplano.infrastructure.db.catalog_repository import SqlCatalogRepository
from sobreplano.infrastructure.db.price_observation_repository import (
    SqlPriceObservationRepository,
)
from sobreplano.infrastructure.db.project_listing_query import SqlProjectListingQuery

pytestmark = pytest.mark.integration


def list_page(
    query: SqlProjectListingQuery,
    *,
    municipality: Municipality | None = None,
    sort: ProjectSort = ProjectSort.NAME,
    limit: int = 50,
    offset: int = 0,
) -> ProjectPage:
    """List with only the municipality as a filter, as the endpoint did before SPEC 07."""
    return query.list_projects(
        filters=ProjectFilters(municipality=municipality), sort=sort, limit=limit, offset=offset
    )


def search(
    query: SqlProjectListingQuery,
    developer: Developer,
    sort: ProjectSort = ProjectSort.NAME,
    **filters: int | Decimal,
) -> ProjectPage:
    """List only the projects of `developer`, so seed data never enters the result."""
    return query.list_projects(
        filters=ProjectFilters(developer=developer.slug, **filters),  # type: ignore[arg-type]
        sort=sort,
        limit=50,
        offset=0,
    )


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

    page = list_page(query, municipality=MUNICIPALITY, limit=50, offset=0)

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

    [listing] = list_page(query, municipality=MUNICIPALITY, limit=50, offset=0).items

    [unit] = listing.unit_types
    assert unit.latest_price is None
    assert unit.price_per_m2_cop is None


def test_unit_types_are_ordered_by_name(
    query: SqlProjectListingQuery, catalog: SqlCatalogRepository, developer: Developer
) -> None:
    project = add_project(catalog, developer, "Proyecto A")
    add_unit_type(catalog, project, "Tipo 02")
    add_unit_type(catalog, project, "Tipo 01", private_area_m2=None, built_area_m2="60.00")

    [listing] = list_page(query, municipality=MUNICIPALITY, limit=50, offset=0).items

    assert [unit.name for unit in listing.unit_types] == ["Tipo 01", "Tipo 02"]
    assert listing.unit_types[0].area_basis == AreaBasis.BUILT


def test_municipality_filter_applies_to_items_and_total(
    query: SqlProjectListingQuery, catalog: SqlCatalogRepository, developer: Developer
) -> None:
    add_project(catalog, developer, "Proyecto A")
    add_project(catalog, developer, "Proyecto B")
    add_project(catalog, developer, "Proyecto C", municipality=OTHER_MUNICIPALITY)

    page = list_page(query, municipality=MUNICIPALITY, limit=50, offset=0)
    other = list_page(query, municipality=OTHER_MUNICIPALITY, limit=50, offset=0)

    assert page.total == 2
    assert [item.name for item in page.items] == ["Proyecto A", "Proyecto B"]
    assert other.total == 1


def test_without_filter_every_municipality_is_counted(
    query: SqlProjectListingQuery, catalog: SqlCatalogRepository, developer: Developer
) -> None:
    before = list_page(query, municipality=None, limit=1, offset=0).total
    add_project(catalog, developer, "Proyecto A")
    add_project(catalog, developer, "Proyecto C", municipality=OTHER_MUNICIPALITY)

    assert list_page(query, municipality=None, limit=1, offset=0).total == before + 2


def test_pagination_keeps_total_and_order(
    query: SqlProjectListingQuery, catalog: SqlCatalogRepository, developer: Developer
) -> None:
    for name in ("Proyecto C", "Proyecto A", "Proyecto B"):
        add_project(catalog, developer, name)

    first = list_page(query, municipality=MUNICIPALITY, limit=2, offset=0)
    second = list_page(query, municipality=MUNICIPALITY, limit=2, offset=2)
    beyond = list_page(query, municipality=MUNICIPALITY, limit=2, offset=10)

    assert [item.name for item in first.items] == ["Proyecto A", "Proyecto B"]
    assert [item.name for item in second.items] == ["Proyecto C"]
    assert first.total == second.total == beyond.total == 3
    assert beyond.items == []


def test_first_price_and_change_come_from_three_days(
    query: SqlProjectListingQuery,
    catalog: SqlCatalogRepository,
    observations: SqlPriceObservationRepository,
    developer: Developer,
) -> None:
    project = add_project(catalog, developer, "Proyecto A")
    unit_type = add_unit_type(catalog, project, "Tipo 01", private_area_m2="50.00")
    # Inserted out of order: the first price is the oldest day, not the first row written.
    add_price(observations, unit_type, 28, 440_000_000, ObservationSource.SCRAPER)
    add_price(observations, unit_type, 26, 400_000_000)
    add_price(observations, unit_type, 27, 420_000_000)

    [listing] = list_page(query, municipality=MUNICIPALITY, limit=50, offset=0).items

    [unit] = listing.unit_types
    assert unit.first_price is not None
    assert unit.first_price.price_cop == 400_000_000
    assert unit.first_price.observed_on == date(2026, 10, 26)
    assert unit.first_price.source == ObservationSource.MANUAL
    assert unit.latest_price is not None
    assert unit.latest_price.source == ObservationSource.SCRAPER
    assert unit.latest_price is not None
    assert unit.latest_price.price_cop == 440_000_000
    assert unit.change_since_first_pct == 10.0


def test_first_price_is_none_without_observations(
    query: SqlProjectListingQuery, catalog: SqlCatalogRepository, developer: Developer
) -> None:
    project = add_project(catalog, developer, "Proyecto A")
    add_unit_type(catalog, project, "Tipo 01")

    [listing] = list_page(query, municipality=MUNICIPALITY, limit=50, offset=0).items

    [unit] = listing.unit_types
    assert unit.first_price is None
    assert unit.change_since_first_pct is None


@pytest.fixture
def priced(
    catalog: SqlCatalogRepository, observations: SqlPriceObservationRepository, developer: Developer
) -> None:
    """Four projects of `developer`:

    - Barato:  2 bedrooms, 40 m², 300M  (and a 4 bedroom, 90 m², 900M unit)
    - Medio:   1 bedroom, 60 m², 500M
    - Caro:    3 bedrooms, 100 m², 800M
    - Sin precio: 2 bedrooms, 50 m², no observations
    """
    barato = add_project(catalog, developer, "Barato")
    add_price(
        observations,
        add_unit_type(catalog, barato, "A", private_area_m2="40.00", bedrooms=2),
        28,
        300_000_000,
    )
    add_price(
        observations,
        add_unit_type(catalog, barato, "B", private_area_m2="90.00", bedrooms=4),
        28,
        900_000_000,
    )
    medio = add_project(catalog, developer, "Medio")
    add_price(
        observations,
        add_unit_type(catalog, medio, "A", private_area_m2="60.00", bedrooms=1),
        28,
        500_000_000,
    )
    caro = add_project(catalog, developer, "Caro")
    add_price(
        observations,
        add_unit_type(catalog, caro, "A", private_area_m2="100.00", bedrooms=3),
        28,
        800_000_000,
    )
    add_unit_type(catalog, add_project(catalog, developer, "Sin precio"), "A")


def names(page: ProjectPage) -> list[str]:
    return [item.name for item in page.items]


@pytest.mark.usefixtures("priced")
def test_no_unit_type_filter_returns_every_project_and_unit_type(
    query: SqlProjectListingQuery, developer: Developer
) -> None:
    page = search(query, developer)

    assert names(page) == ["Barato", "Caro", "Medio", "Sin precio"]
    assert page.total == 4
    assert [len(item.unit_types) for item in page.items] == [2, 1, 1, 1]


@pytest.mark.usefixtures("priced")
def test_max_price_keeps_only_matching_unit_types(
    query: SqlProjectListingQuery, developer: Developer
) -> None:
    page = search(query, developer, max_price=500_000_000)

    assert names(page) == ["Barato", "Medio"]
    assert page.total == 2
    # The 900M unit of Barato does not match, so it is not in the response.
    assert [u.name for u in page.items[0].unit_types] == ["A"]


@pytest.mark.usefixtures("priced")
def test_min_price_alone(query: SqlProjectListingQuery, developer: Developer) -> None:
    page = search(query, developer, min_price=800_000_000)

    assert names(page) == ["Barato", "Caro"]
    assert [u.name for u in page.items[0].unit_types] == ["B"]


@pytest.mark.usefixtures("priced")
def test_min_bedrooms_alone(query: SqlProjectListingQuery, developer: Developer) -> None:
    page = search(query, developer, min_bedrooms=3)

    assert names(page) == ["Barato", "Caro"]
    assert page.total == 2


@pytest.mark.usefixtures("priced")
def test_area_range_alone(query: SqlProjectListingQuery, developer: Developer) -> None:
    page = search(query, developer, min_area=Decimal("50"), max_area=Decimal("95"))

    # Medio (60), Barato B (90) and Sin precio (50); Barato A (40) and Caro (100) are out.
    assert names(page) == ["Barato", "Medio", "Sin precio"]


@pytest.mark.usefixtures("priced")
def test_filters_must_hold_in_the_same_unit_type(
    query: SqlProjectListingQuery, developer: Developer
) -> None:
    # Barato has a cheap unit (2 bedrooms) and a big one (4 bedrooms) but none with 3 or more
    # bedrooms under 500M, so it must not match even though each filter holds somewhere.
    page = search(query, developer, min_bedrooms=3, max_price=500_000_000)

    assert page.items == []
    assert page.total == 0


@pytest.mark.usefixtures("priced")
def test_combined_filters(query: SqlProjectListingQuery, developer: Developer) -> None:
    page = search(query, developer, min_bedrooms=2, max_price=400_000_000)

    [barato] = page.items
    assert barato.name == "Barato"
    assert [u.name for u in barato.unit_types] == ["A"]
    assert page.total == 1


@pytest.mark.usefixtures("priced")
def test_unit_type_without_price_meets_no_price_filter(
    query: SqlProjectListingQuery, developer: Developer
) -> None:
    assert "Sin precio" not in names(search(query, developer, max_price=10_000_000_000))
    assert "Sin precio" not in names(search(query, developer, min_price=1))
    # Without a price filter it is still listed.
    assert "Sin precio" in names(search(query, developer, min_bedrooms=2))


@pytest.mark.usefixtures("priced")
def test_sort_by_price_puts_cheapest_first_and_unpriced_last(
    query: SqlProjectListingQuery, developer: Developer
) -> None:
    page = search(query, developer, ProjectSort.PRICE)

    assert names(page) == ["Barato", "Medio", "Caro", "Sin precio"]
    assert page.total == 4


@pytest.mark.usefixtures("priced")
def test_sort_by_price_uses_only_unit_types_that_match(
    query: SqlProjectListingQuery, developer: Developer
) -> None:
    # With min_price=400M Barato matches only through its 900M unit, so it moves after Medio.
    page = search(query, developer, ProjectSort.PRICE, min_price=400_000_000)

    assert names(page) == ["Medio", "Caro", "Barato"]


@pytest.mark.usefixtures("priced")
def test_sort_by_price_without_price_filters_is_stable_by_name(
    query: SqlProjectListingQuery, catalog: SqlCatalogRepository, developer: Developer
) -> None:
    add_unit_type(catalog, add_project(catalog, developer, "Aaa sin tipologias"), "A")

    page = search(query, developer, ProjectSort.PRICE)

    assert names(page)[-2:] == ["Aaa sin tipologias", "Sin precio"]


def test_unknown_developer_gives_an_empty_page(query: SqlProjectListingQuery) -> None:
    page = query.list_projects(
        filters=ProjectFilters(developer=f"no-existe-{uuid4().hex}"),
        sort=ProjectSort.NAME,
        limit=50,
        offset=0,
    )

    assert page.items == []
    assert page.total == 0


@pytest.mark.usefixtures("priced")
def test_total_ignores_pagination_with_filters(
    query: SqlProjectListingQuery, developer: Developer
) -> None:
    page = query.list_projects(
        filters=ProjectFilters(developer=developer.slug, max_price=1_000_000_000),
        sort=ProjectSort.PRICE,
        limit=1,
        offset=1,
    )

    assert names(page) == ["Medio"]
    assert page.total == 3


@pytest.mark.usefixtures("priced")
def test_developer_filter_excludes_other_developers(
    query: SqlProjectListingQuery, catalog: SqlCatalogRepository, developer: Developer
) -> None:
    other = Developer(
        id=uuid4(), name="Otra", slug=f"dev-{uuid4().hex[:8]}", website_url="https://example.com"
    )
    catalog.add_developer(other)
    add_project(catalog, other, "De otra")

    assert "De otra" not in names(search(query, developer))
    assert names(search(query, other)) == ["De otra"]


def test_get_project_returns_history_oldest_first(
    query: SqlProjectListingQuery,
    catalog: SqlCatalogRepository,
    observations: SqlPriceObservationRepository,
    developer: Developer,
) -> None:
    project = add_project(catalog, developer, "Proyecto A")
    tipo_2 = add_unit_type(catalog, project, "Tipo 02")
    tipo_1 = add_unit_type(catalog, project, "Tipo 01")
    add_price(observations, tipo_2, 28, 700_000_000, ObservationSource.SCRAPER)
    add_price(observations, tipo_2, 26, 680_000_000)
    add_price(observations, tipo_1, 27, 500_000_000)

    detail = query.get_project(project.slug)

    assert detail is not None
    assert detail.project.slug == project.slug
    assert detail.project.developer_slug == developer.slug
    assert detail.project.location == GeoPoint(lat=6.1735, lon=-75.5925)
    assert [u.listing.name for u in detail.unit_types] == ["Tipo 01", "Tipo 02"]
    first, second = detail.unit_types
    assert [(p.observed_on, p.price_cop, p.source) for p in second.history] == [
        (date(2026, 10, 26), 680_000_000, ObservationSource.MANUAL),
        (date(2026, 10, 28), 700_000_000, ObservationSource.SCRAPER),
    ]
    assert len(first.history) == 1
    # The history of one unit type never leaks into another.
    assert first.history[0].price_cop == 500_000_000
    assert second.listing.latest_price is not None
    assert second.listing.latest_price.price_cop == 700_000_000
    assert second.listing.change_since_first_pct == 2.9


def test_get_project_without_location_or_prices(
    query: SqlProjectListingQuery, catalog: SqlCatalogRepository, developer: Developer
) -> None:
    project = add_project(catalog, developer, "Proyecto A", location=None)
    add_unit_type(catalog, project, "Tipo 01")

    detail = query.get_project(project.slug)

    assert detail is not None
    assert detail.project.location is None
    [unit] = detail.unit_types
    assert unit.history == []
    assert unit.listing.first_price is None


def test_get_project_without_unit_types(
    query: SqlProjectListingQuery, catalog: SqlCatalogRepository, developer: Developer
) -> None:
    project = add_project(catalog, developer, "Proyecto A")

    detail = query.get_project(project.slug)

    assert detail is not None
    assert detail.unit_types == []


def test_get_project_unknown_slug_is_none(query: SqlProjectListingQuery) -> None:
    assert query.get_project(f"no-existe-{uuid4().hex[:8]}") is None


def test_list_developers_counts_projects_and_orders_by_name(
    query: SqlProjectListingQuery, catalog: SqlCatalogRepository, developer: Developer
) -> None:
    empty = Developer(
        id=uuid4(), name="Aaa sin proyectos", slug=f"dev-{uuid4().hex[:8]}", website_url="https://a"
    )
    catalog.add_developer(empty)
    add_project(catalog, developer, "Proyecto A")
    add_project(catalog, developer, "Proyecto B")

    summaries = query.list_developers()

    by_slug = {summary.slug: summary for summary in summaries}
    assert by_slug[developer.slug].projects == 2
    assert by_slug[developer.slug].name == developer.name
    assert by_slug[empty.slug].projects == 0
    assert [s.name for s in summaries] == sorted(s.name for s in summaries)
