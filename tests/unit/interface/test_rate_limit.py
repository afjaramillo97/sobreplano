"""Rate limits through the routes, with an in-memory counter and a fixed clock: no database."""

import logging
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from sobreplano.domain.advisor import AdvisorAnswer, AdvisorReply
from sobreplano.domain.errors import RateLimitStoreError
from sobreplano.domain.listings import (
    DeveloperSummary,
    ProjectDetail,
    ProjectFilters,
    ProjectPage,
    ProjectSort,
)
from sobreplano.domain.rate_limit import ClientUsage, WindowCounts
from sobreplano.infrastructure.settings import Settings
from sobreplano.interface.api.dependencies import (
    get_ask_advisor,
    get_project_listing_query,
    get_session,
)
from sobreplano.interface.api.main import create_app
from sobreplano.interface.api.rate_limit import RateLimiter, client_ip, get_rate_limiter

UNUSED_URL = "postgresql+psycopg://unused@127.0.0.1:1/unused"
START = datetime(2026, 11, 14, 15, 0, 20, tzinfo=UTC)  # 10:00:20 in Bogotá


class InMemoryCounters:
    """Same contract as SqlRateLimitRepository, in a dict; `down` makes every call fail."""

    def __init__(self) -> None:
        self.hits: dict[tuple[str, str, str, datetime], int] = {}
        self.down = False

    def hit(
        self, bucket: str, client_key: str, minute_start: datetime, day_start: datetime
    ) -> WindowCounts:
        if self.down:
            raise RateLimitStoreError("counters down")
        counts: list[int] = []
        for kind, start in (("minute", minute_start), ("day", day_start)):
            key = (bucket, kind, client_key, start)
            self.hits[key] = self.hits.get(key, 0) + 1
            counts.append(self.hits[key])
        return WindowCounts(minute=counts[0], day=counts[1])

    def prune(self, before: datetime) -> int:
        return 0

    def usage_since(self, since: datetime) -> list[ClientUsage]:
        return []


class EmptyQuery:
    def list_projects(
        self, *, filters: ProjectFilters, sort: ProjectSort, limit: int, offset: int
    ) -> ProjectPage:
        return ProjectPage(items=[], total=0)

    def get_project(self, slug: str) -> ProjectDetail | None:
        return None

    def list_developers(self) -> list[DeveloperSummary]:
        return []


class CountingAdvisor:
    """Stands for AskAdvisor: answers and counts how many messages reached it."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, thread_id: UUID | None, message: str, today: date) -> AdvisorAnswer:
        self.calls += 1
        reply = AdvisorReply(text="Hola.", tools_used=[], llm_calls=[], tool_calls=[])
        return AdvisorAnswer(thread_id=uuid4(), reply=reply)


class FakeSession:
    def commit(self) -> None:
        pass


class Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now


class World:
    def __init__(self, **settings: Any) -> None:
        self.counters = InMemoryCounters()
        self.clock = Clock()
        self.settings = Settings(database_url=UNUSED_URL, **settings)
        self.limiter = RateLimiter(self.counters, self.settings, self.clock)
        self.advisor = CountingAdvisor()

    def client(self) -> TestClient:
        app = create_app(self.settings)
        app.dependency_overrides[get_rate_limiter] = lambda: self.limiter
        app.dependency_overrides[get_project_listing_query] = EmptyQuery
        app.dependency_overrides[get_ask_advisor] = lambda: self.advisor
        app.dependency_overrides[get_session] = FakeSession
        return TestClient(app)


@pytest.fixture
def world() -> World:
    return World()


@pytest.fixture
def client(world: World) -> Iterator[TestClient]:
    with world.client() as client:
        yield client


def detail(client: TestClient, headers: dict[str, str] | None = None) -> int:
    return client.get("/projects/alpha", headers=headers).status_code


# The limit through the routes


def test_ten_details_a_minute_pass_and_the_eleventh_gets_429_with_retry_after(
    client: TestClient,
) -> None:
    codes = [detail(client) for _ in range(10)]
    assert codes == [404] * 10  # the project does not exist, but each request counts
    response = client.get("/projects/alpha")
    assert response.status_code == 429
    assert response.json() == {"detail": "too many requests"}
    assert response.headers["Retry-After"] == "40"  # 10:00:20 → 10:01:00


def test_the_next_minute_lets_requests_through_again(client: TestClient, world: World) -> None:
    for _ in range(11):
        detail(client)
    world.clock.now += timedelta(minutes=1)
    assert detail(client) == 404


def test_the_forty_first_detail_of_the_day_gets_429_until_bogota_midnight(
    client: TestClient, world: World
) -> None:
    for _ in range(40):
        assert detail(client) == 404
        world.clock.now += timedelta(minutes=1)  # never over the minute limit
    response = client.get("/projects/alpha")
    assert response.status_code == 429
    # 40 minutes after 10:00:20 Bogotá is 10:40:20; midnight is 13 h 19 min 40 s away.
    assert response.headers["Retry-After"] == str(13 * 3600 + 19 * 60 + 40)


def test_the_day_resets_at_bogota_midnight_not_at_utc_midnight(
    client: TestClient, world: World
) -> None:
    world.clock.now = datetime(2026, 11, 14, 23, 0, tzinfo=UTC)  # 18:00 in Bogotá
    for _ in range(40):
        detail(client)
        world.clock.now += timedelta(minutes=1)
    world.clock.now = datetime(2026, 11, 15, 1, 0, tzinfo=UTC)  # UTC midnight passed
    assert detail(client) == 429
    world.clock.now = datetime(2026, 11, 15, 5, 0, tzinfo=UTC)  # Bogotá midnight
    assert detail(client) == 404


def test_list_routes_share_one_limit_apart_from_the_detail(client: TestClient) -> None:
    for _ in range(15):
        assert client.get("/projects").status_code == 200
        assert client.get("/developers").status_code == 200
    assert client.get("/projects").status_code == 429  # 31st list request this minute
    assert detail(client) == 404  # the detail has its own count


def test_the_advisor_allows_five_messages_a_minute_and_the_sixth_never_reaches_it(
    client: TestClient, world: World
) -> None:
    codes = [client.post("/advisor/chat", json={"message": "hola"}).status_code for _ in range(6)]
    assert codes == [200] * 5 + [429]
    assert world.advisor.calls == 5


def test_the_docs_have_no_limit(client: TestClient, world: World) -> None:
    world.counters.down = True  # a counted route would log; the docs never ask
    for _ in range(50):
        assert client.get("/openapi.json").status_code == 200
    assert world.counters.hits == {}


def test_disabled_limits_count_nothing() -> None:
    world = World(rate_limits_enabled=False)
    with world.client() as client:
        assert all(detail(client) == 404 for _ in range(20))
    assert world.counters.hits == {}


# When the counters are down


def test_reads_are_served_and_the_advisor_refused_when_the_counters_are_down(
    client: TestClient, world: World, caplog: pytest.LogCaptureFixture
) -> None:
    world.counters.down = True
    assert client.get("/projects").status_code == 200
    assert client.get("/developers").status_code == 200
    assert detail(client) == 404
    response = client.post("/advisor/chat", json={"message": "hola"})
    assert response.status_code == 503
    assert world.advisor.calls == 0
    assert "rate limit store down, serving bucket=list" in caplog.text
    assert "rate limit store down, refusing bucket=advisor" in caplog.text


# Clients


def test_clients_are_told_apart_by_ip_behind_a_trusted_proxy() -> None:
    world = World(trusted_proxy_hops=1)
    with world.client() as client:
        for _ in range(10):
            detail(client, {"X-Forwarded-For": "203.0.113.7"})
        assert detail(client, {"X-Forwarded-For": "203.0.113.7"}) == 429
        assert detail(client, {"X-Forwarded-For": "198.51.100.2"}) == 404


def test_without_a_trusted_proxy_a_forged_header_does_not_reset_the_count(
    client: TestClient,
) -> None:
    for i in range(10):
        detail(client, {"X-Forwarded-For": f"10.0.0.{i}"})
    assert detail(client, {"X-Forwarded-For": "10.0.0.99"}) == 429


@pytest.mark.parametrize(
    ("host", "forwarded", "hops", "expected"),
    [
        ("10.0.0.1", "203.0.113.7", 0, "10.0.0.1"),  # no trusted proxy: header ignored
        ("10.0.0.1", "203.0.113.7", 1, "203.0.113.7"),
        ("10.0.0.1", "1.1.1.1, 203.0.113.7", 1, "203.0.113.7"),  # the left entry is forged
        ("10.0.0.1", "1.1.1.1, 203.0.113.7, 10.0.0.9", 2, "203.0.113.7"),
        ("10.0.0.1", "203.0.113.7", 2, "10.0.0.1"),  # fewer entries than hops
        ("10.0.0.1", None, 1, "10.0.0.1"),
        (None, None, 0, "unknown"),
    ],
)
def test_client_ip(host: str | None, forwarded: str | None, hops: int, expected: str) -> None:
    assert client_ip(host, forwarded, hops) == expected


def test_the_client_key_is_a_keyed_hash_never_the_ip(world: World) -> None:
    key = world.limiter.client_key("203.0.113.7")
    assert len(key) == 32
    assert int(key, 16) >= 0  # hexadecimal
    assert "203" not in key
    assert key == world.limiter.client_key("203.0.113.7")
    assert key != world.limiter.client_key("203.0.113.8")
    other = RateLimiter(
        InMemoryCounters(), Settings(database_url=UNUSED_URL, rate_limit_key=SecretStr("secret"))
    )
    assert other.client_key("203.0.113.7") != key


def test_the_stored_keys_and_the_log_never_show_the_ip(
    world: World, caplog: pytest.LogCaptureFixture
) -> None:
    world.settings = Settings(database_url=UNUSED_URL, trusted_proxy_hops=1)
    world.limiter = RateLimiter(world.counters, world.settings, world.clock)
    with caplog.at_level(logging.WARNING), world.client() as client:
        for _ in range(11):
            detail(client, {"X-Forwarded-For": "203.0.113.7"})
    key = world.limiter.client_key("203.0.113.7")
    assert {stored for _, _, stored, _ in world.counters.hits} == {key}
    assert f"rate_limited bucket=detail window=minute client={key[:8]}" in caplog.text
    assert "203.0.113.7" not in caplog.text


def test_a_missing_key_logs_a_warning(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        RateLimiter(InMemoryCounters(), Settings(database_url=UNUSED_URL))
    assert "RATE_LIMIT_KEY is not set" in caplog.text
