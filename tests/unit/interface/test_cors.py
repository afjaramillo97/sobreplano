"""CORS of the API (SPEC 11a, 11c): explicit origins only, GET and the advisor's POST, Retry-After
readable on a 429."""

from collections.abc import Iterator

import httpx2
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from sobreplano.domain.listings import (
    DeveloperSummary,
    ProjectDetail,
    ProjectFilters,
    ProjectPage,
    ProjectSort,
)
from sobreplano.infrastructure.settings import Settings
from sobreplano.interface.api.dependencies import get_project_listing_query
from sobreplano.interface.api.main import create_app
from sobreplano.interface.api.rate_limit import limit_advisor, limit_detail, limit_list

UNUSED_URL = "postgresql+psycopg://unused@127.0.0.1:1/unused"
SITE = "http://localhost:4321"
STRANGER = "https://evil.example"


class EmptyQuery:
    def list_projects(
        self, *, filters: ProjectFilters, sort: ProjectSort, limit: int, offset: int
    ) -> ProjectPage:
        return ProjectPage(items=[], total=0)

    def get_project(self, slug: str) -> ProjectDetail | None:
        return None

    def list_developers(self) -> list[DeveloperSummary]:
        return []


class AdvisorLimitCounter:
    """Stands for the advisor's rate limit and counts the requests that reached it."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> None:
        self.calls += 1


advisor_limit = AdvisorLimitCounter()


def make_client(origins: list[str]) -> TestClient:
    app = create_app(Settings(database_url=UNUSED_URL, cors_allowed_origins=origins))
    app.dependency_overrides[get_project_listing_query] = EmptyQuery
    app.dependency_overrides[limit_list] = lambda: None
    app.dependency_overrides[limit_detail] = always_limited
    app.dependency_overrides[limit_advisor] = advisor_limit
    return TestClient(app)


def always_limited() -> None:
    raise HTTPException(429, detail="too many requests", headers={"Retry-After": "120"})


@pytest.fixture
def client() -> Iterator[TestClient]:
    with make_client([SITE]) as client:
        yield client


def test_an_allowed_origin_can_read_the_list(client: TestClient) -> None:
    response = client.get("/projects?limit=1", headers={"Origin": SITE})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == SITE
    assert "access-control-allow-credentials" not in response.headers


def test_a_foreign_origin_gets_no_cors_header(client: TestClient) -> None:
    response = client.get("/projects?limit=1", headers={"Origin": STRANGER})
    assert response.status_code == 200  # CORS is enforced by the browser, not the server
    assert "access-control-allow-origin" not in response.headers


def test_a_429_exposes_retry_after_to_the_browser(client: TestClient) -> None:
    response = client.get("/projects/alpha", headers={"Origin": SITE})
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "120"
    assert response.headers["access-control-allow-origin"] == SITE
    assert response.headers["access-control-expose-headers"] == "Retry-After"


def preflight(
    client: TestClient, path: str, origin: str, method: str, **headers: str
) -> httpx2.Response:
    return client.options(
        path,
        headers={"Origin": origin, "Access-Control-Request-Method": method, **headers},
    )


def test_preflight_allows_get(client: TestClient) -> None:
    response = preflight(client, "/projects", SITE, "GET")
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == SITE


def test_preflight_of_the_advisor_post_passes_without_counting(client: TestClient) -> None:
    before = advisor_limit.calls
    response = preflight(
        client,
        "/advisor/chat/stream",
        SITE,
        "POST",
        **{"Access-Control-Request-Headers": "content-type"},
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == SITE
    assert "POST" in response.headers["access-control-allow-methods"]
    assert "content-type" in response.headers["access-control-allow-headers"].lower()
    assert "access-control-allow-credentials" not in response.headers
    # The middleware answers the preflight; it never reaches the advisor's limit.
    assert advisor_limit.calls == before


def test_preflight_from_a_foreign_origin_is_refused(client: TestClient) -> None:
    response = preflight(client, "/advisor/chat/stream", STRANGER, "POST")
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize("method", ["PUT", "DELETE", "PATCH"])
def test_preflight_of_other_methods_is_refused(client: TestClient, method: str) -> None:
    assert preflight(client, "/advisor/chat", SITE, method).status_code == 400


def test_preflight_with_an_unlisted_header_is_refused(client: TestClient) -> None:
    response = preflight(
        client,
        "/advisor/chat/stream",
        SITE,
        "POST",
        **{"Access-Control-Request-Headers": "authorization"},
    )
    assert response.status_code == 400


def test_an_empty_list_adds_no_cors_at_all() -> None:
    with make_client([]) as client:
        response = client.get("/projects?limit=1", headers={"Origin": SITE})
        assert "access-control-allow-origin" not in response.headers
        preflight = client.options(
            "/projects",
            headers={"Origin": SITE, "Access-Control-Request-Method": "GET"},
        )
        assert preflight.status_code == 405  # no middleware answers the preflight
