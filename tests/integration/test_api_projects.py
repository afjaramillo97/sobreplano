"""Integration tests for GET /projects."""

import pytest
from factories import (
    MUNICIPALITY,
    OTHER_MUNICIPALITY,
    add_price,
    add_project,
    add_unit_type,
)
from fastapi.testclient import TestClient

from sobreplano.domain.catalog import Developer
from sobreplano.infrastructure.db.catalog_repository import SqlCatalogRepository
from sobreplano.infrastructure.db.price_observation_repository import (
    SqlPriceObservationRepository,
)

pytestmark = pytest.mark.integration


def test_listing_matches_the_contract(
    client: TestClient,
    catalog: SqlCatalogRepository,
    observations: SqlPriceObservationRepository,
    developer: Developer,
) -> None:
    project = add_project(catalog, developer, "AXIS - Ciudad Peldar")
    unit_type = add_unit_type(catalog, project, "Tipo 02", private_area_m2="54.98")
    add_price(observations, unit_type, 28, 716_500_000)

    response = client.get("/projects", params={"municipality": MUNICIPALITY})

    assert response.status_code == 200
    body = response.json()
    assert (body["total"], body["limit"], body["offset"]) == (1, 50, 0)
    [item] = body["items"]
    assert item["slug"] == project.slug
    assert item["developer"] == {"name": developer.name, "slug": developer.slug}
    assert item["municipality"] == "itagui"
    assert item["location"] == {"lat": 6.1735, "lon": -75.5925}
    [unit] = item["unit_types"]
    assert unit["private_area_m2"] == 54.98  # a JSON number, not a string
    assert unit["built_area_m2"] is None
    assert unit["latest_price"] == {
        "price_cop": 716_500_000,
        "observed_on": "2026-10-28",
        "source": "manual",
    }
    assert unit["price_per_m2_cop"] == round(716_500_000 / 54.98)
    assert unit["area_basis"] == "private"


def test_unit_type_without_price_has_null_price_fields(
    client: TestClient, catalog: SqlCatalogRepository, developer: Developer
) -> None:
    add_unit_type(catalog, add_project(catalog, developer, "Proyecto A"), "Tipo 01")

    [item] = client.get("/projects", params={"municipality": MUNICIPALITY}).json()["items"]

    [unit] = item["unit_types"]
    assert unit["latest_price"] is None
    assert unit["price_per_m2_cop"] is None


def test_municipality_filter(
    client: TestClient, catalog: SqlCatalogRepository, developer: Developer
) -> None:
    add_project(catalog, developer, "Proyecto A")
    add_project(catalog, developer, "Proyecto B", municipality=OTHER_MUNICIPALITY)

    body = client.get("/projects", params={"municipality": OTHER_MUNICIPALITY}).json()

    assert body["total"] == 1
    assert [item["name"] for item in body["items"]] == ["Proyecto B"]


def test_pagination_echoes_limit_and_offset(
    client: TestClient, catalog: SqlCatalogRepository, developer: Developer
) -> None:
    for name in ("Proyecto A", "Proyecto B", "Proyecto C"):
        add_project(catalog, developer, name)

    body = client.get(
        "/projects", params={"municipality": MUNICIPALITY, "limit": 2, "offset": 1}
    ).json()

    assert (body["total"], body["limit"], body["offset"]) == (3, 2, 1)
    assert [item["name"] for item in body["items"]] == ["Proyecto B", "Proyecto C"]


@pytest.mark.parametrize(
    "params",
    [
        {"municipality": "nope"},
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
    ],
)
def test_invalid_query_params_give_422(client: TestClient, params: dict[str, str | int]) -> None:
    assert client.get("/projects", params=params).status_code == 422


def test_openapi_lists_both_routes(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]

    assert sorted(paths) == ["/health", "/projects"]
