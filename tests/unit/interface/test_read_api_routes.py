"""Contract of the read API routes with an in-memory query: no database, no mocks."""

from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from sobreplano.domain.catalog import GeoPoint, Municipality
from sobreplano.domain.listings import (
    DeveloperSummary,
    LatestPrice,
    PricePoint,
    ProjectDetail,
    ProjectFilters,
    ProjectListing,
    ProjectPage,
    ProjectSort,
    UnitTypeDetail,
    UnitTypeListing,
)
from sobreplano.domain.pricing import ObservationSource
from sobreplano.infrastructure.settings import Settings
from sobreplano.interface.api.dependencies import get_project_listing_query
from sobreplano.interface.api.main import create_app

FIRST = PricePoint(date(2026, 10, 28), 716_500_000, ObservationSource.MANUAL)
LAST = PricePoint(date(2026, 11, 3), 716_500_000, ObservationSource.SCRAPER)
UNIT = UnitTypeListing(
    id=uuid4(),
    name="Tipo 02",
    private_area_m2=Decimal("54.98"),
    built_area_m2=None,
    bedrooms=2,
    bathrooms=2,
    latest_price=LatestPrice(LAST.price_cop, LAST.observed_on, LAST.source),
    first_price=FIRST,
)
PROJECT = ProjectListing(
    id=uuid4(),
    slug="axis-ciudad-peldar",
    name="AXIS - Ciudad Peldar",
    developer_name="Constructora Capital",
    developer_slug="constructora-capital",
    municipality=Municipality.ENVIGADO,
    neighborhood="Las Vegas",
    location=GeoPoint(lat=6.1735, lon=-75.5925),
    source_url="https://example.com/axis",
    unit_types=[UNIT],
)


class FakeQuery:
    """Answers with one fixed project and records the filters it receives."""

    def __init__(self) -> None:
        self.filters: ProjectFilters | None = None
        self.sort: ProjectSort | None = None

    def list_projects(
        self, *, filters: ProjectFilters, sort: ProjectSort, limit: int, offset: int
    ) -> ProjectPage:
        self.filters, self.sort = filters, sort
        return ProjectPage(items=[PROJECT], total=1)

    def get_project(self, slug: str) -> ProjectDetail | None:
        if slug != PROJECT.slug:
            return None
        return ProjectDetail(PROJECT, [UnitTypeDetail(UNIT, [FIRST, LAST])])

    def list_developers(self) -> list[DeveloperSummary]:
        return [DeveloperSummary("constructora-capital", "Constructora Capital", "https://c", 25)]


@pytest.fixture
def fake() -> FakeQuery:
    return FakeQuery()


@pytest.fixture
def client(fake: FakeQuery) -> Iterator[TestClient]:
    app = create_app(Settings(database_url="postgresql+psycopg://unused@127.0.0.1:1/unused"))
    app.dependency_overrides[get_project_listing_query] = lambda: fake
    with TestClient(app) as client:
        yield client


def test_detail_matches_the_contract(client: TestClient) -> None:
    response = client.get("/projects/axis-ciudad-peldar")

    assert response.status_code == 200
    body = response.json()
    assert body["developer"] == {"name": "Constructora Capital", "slug": "constructora-capital"}
    assert body["location"] == {"lat": 6.1735, "lon": -75.5925}
    [unit] = body["unit_types"]
    assert unit["first_price"] == {
        "price_cop": 716_500_000,
        "observed_on": "2026-10-28",
        "source": "manual",
    }
    assert unit["change_since_first_pct"] == 0.0
    assert unit["history"] == [
        {"observed_on": "2026-10-28", "price_cop": 716_500_000, "source": "manual"},
        {"observed_on": "2026-11-03", "price_cop": 716_500_000, "source": "scraper"},
    ]


def test_unknown_slug_is_404(client: TestClient) -> None:
    response = client.get("/projects/no-existe")

    assert response.status_code == 404
    assert response.json() == {"detail": "project not found"}


@pytest.mark.parametrize("slug", ["NO_VALIDO", "con_guion_bajo", "a" * 81, "Mayuscula"])
def test_badly_formed_slug_is_422(client: TestClient, slug: str) -> None:
    assert client.get(f"/projects/{slug}").status_code == 422


def test_listing_exposes_first_price_and_change(client: TestClient) -> None:
    [item] = client.get("/projects").json()["items"]

    [unit] = item["unit_types"]
    assert unit["first_price"]["observed_on"] == "2026-10-28"
    assert unit["change_since_first_pct"] == 0.0
    assert "history" not in unit


def test_listing_passes_filters_and_sort_to_the_query(client: TestClient, fake: FakeQuery) -> None:
    response = client.get(
        "/projects",
        params={
            "developer": "constructora-capital",
            "max_price": 500_000_000,
            "min_bedrooms": 2,
            "min_area": "40.5",
            "sort": "price",
            "municipality": "envigado",
        },
    )

    assert response.status_code == 200
    assert fake.sort == ProjectSort.PRICE
    assert fake.filters == ProjectFilters(
        municipality=Municipality.ENVIGADO,
        developer="constructora-capital",
        max_price=500_000_000,
        min_bedrooms=2,
        min_area=Decimal("40.5"),
    )


@pytest.mark.parametrize(
    "params",
    [
        {"min_price": 900_000_000, "max_price": 100_000_000},
        {"min_area": 80, "max_area": 40},
        {"min_price": 0},
        {"min_bedrooms": -1},
        {"max_area": 0},
        {"sort": "rise"},
    ],
)
def test_invalid_filters_are_422(client: TestClient, params: dict[str, int | str]) -> None:
    assert client.get("/projects", params=params).status_code == 422


def test_developers_matches_the_contract(client: TestClient) -> None:
    response = client.get("/developers")

    assert response.status_code == 200
    assert response.json() == [
        {
            "slug": "constructora-capital",
            "name": "Constructora Capital",
            "website_url": "https://c",
            "projects": 25,
        }
    ]
