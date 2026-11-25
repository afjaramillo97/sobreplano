"""Contract of POST /advisor/chat/stream with in-memory doubles: no database, no model."""

import json
import threading
from collections.abc import Callable, Generator, Iterator
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from test_rate_limit import Clock, InMemoryCounters

from sobreplano.application.ask_advisor import AskAdvisor
from sobreplano.domain.advisor import AdvisorReply, AdvisorStep, LlmCall
from sobreplano.domain.errors import AdvisorLimitError, AdvisorUnavailableError
from sobreplano.infrastructure.settings import Settings
from sobreplano.interface.api.dependencies import get_advisor_opener
from sobreplano.interface.api.main import create_app
from sobreplano.interface.api.rate_limit import RateLimiter, get_rate_limiter
from sobreplano.interface.api.routes import advisor as advisor_route

UNUSED_URL = "postgresql+psycopg://unused@127.0.0.1:1/unused"
CALL = LlmCall(
    model="openai:gpt-6-luna",
    input_tokens=10,
    output_tokens=5,
    cost_usd=Decimal("0.01"),
    prompt_version="cd741d6427ec",
)


class FakeAgent:
    """Runs search_projects and get_project, telling on_step, then answers."""

    def __init__(self) -> None:
        self.error: Exception | None = None
        self.release: threading.Event | None = None  # when set, waits for it before answering
        self.messages: list[str] = []

    def reply(
        self,
        thread_id: UUID,
        message: str,
        on_step: Callable[[AdvisorStep], None] | None = None,
    ) -> AdvisorReply:
        self.messages.append(message)
        for tool in ("search_projects", "get_project"):
            if on_step is not None:
                on_step(AdvisorStep(tool=tool, phase="start"))
                on_step(AdvisorStep(tool=tool, phase="end"))
        if self.release is not None:
            self.release.wait(timeout=5)
        if self.error is not None:
            raise self.error
        return AdvisorReply(
            text="Arrayanes del Sur es el más barato.",
            tools_used=["search_projects", "get_project"],
            llm_calls=[CALL],
            tool_calls=[],
            projects=["arrayanes-del-sur"],
        )


class InMemoryUsage:
    def __init__(self) -> None:
        self.spent = Decimal(0)
        self.rows: list[LlmCall] = []

    def add(self, feature: str, call: LlmCall, thread_id: UUID | None) -> None:
        self.rows.append(call)

    def cost_on(self, feature: str, day: date) -> Decimal:
        return self.spent


class InMemoryThreads:
    def __init__(self) -> None:
        self.turns: dict[UUID, int] = {}

    def create(self) -> UUID:
        thread_id = uuid4()
        self.turns[thread_id] = 0
        return thread_id

    def get_turns(self, thread_id: UUID) -> int | None:
        return self.turns.get(thread_id)

    def record_turn(self, thread_id: UUID) -> None:
        self.turns[thread_id] += 1

    def list_inactive_since(self, cutoff: datetime) -> list[UUID]:
        return []

    def delete(self, thread_id: UUID) -> None:
        del self.turns[thread_id]


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1


class World:
    def __init__(self, **settings: Any) -> None:
        self.agent = FakeAgent()
        self.usage = InMemoryUsage()
        self.threads = InMemoryThreads()
        self.session = FakeSession()
        self.opened = 0
        self.ask = AskAdvisor(
            self.agent, self.usage, self.threads, daily_budget_usd=Decimal("0.20"), max_turns=20
        )
        self.settings = Settings(database_url=UNUSED_URL, **settings)
        self.limiter = RateLimiter(InMemoryCounters(), self.settings, Clock())

    @contextmanager
    def open_advisor(self) -> Generator[tuple[AskAdvisor, FakeSession]]:
        self.opened += 1
        yield self.ask, self.session

    def client(self) -> TestClient:
        app = create_app(self.settings)
        app.dependency_overrides[get_advisor_opener] = lambda: self.open_advisor
        app.dependency_overrides[get_rate_limiter] = lambda: self.limiter
        return TestClient(app)


@pytest.fixture
def world() -> World:
    return World()


@pytest.fixture
def client(world: World) -> Iterator[TestClient]:
    with world.client() as client:
        yield client


def parse_events(text: str) -> list[tuple[str, dict[str, Any]]]:
    """(event, data) of each SSE event; comments such as the ping are skipped."""
    events: list[tuple[str, dict[str, Any]]] = []
    for block in text.strip().split("\n\n"):
        fields = dict(
            line.split(": ", 1) for line in block.splitlines() if not line.startswith(":")
        )
        if fields:
            events.append((fields["event"], json.loads(fields["data"])))
    return events


def stream(client: TestClient, body: dict[str, object]) -> list[tuple[str, dict[str, Any]]]:
    response = client.post("/advisor/chat/stream", json=body)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    return parse_events(response.text)


def test_steps_come_in_order_and_the_answer_last(client: TestClient, world: World) -> None:
    events = stream(client, {"message": "¿Cuál es el más barato?"})

    assert events[:-1] == [
        ("step", {"tool": "search_projects", "phase": "start"}),
        ("step", {"tool": "search_projects", "phase": "end"}),
        ("step", {"tool": "get_project", "phase": "start"}),
        ("step", {"tool": "get_project", "phase": "end"}),
    ]
    name, answer = events[-1]
    assert name == "answer"
    assert answer == {
        "thread_id": answer["thread_id"],
        "reply": "Arrayanes del Sur es el más barato.",
        "tools_used": ["search_projects", "get_project"],
        "projects": ["arrayanes-del-sur"],
        "remaining_today": 29,
    }
    assert world.threads.turns == {UUID(answer["thread_id"]): 1}
    assert world.usage.rows == [CALL]
    assert world.session.commits == 1


def test_the_stream_is_not_cached_nor_buffered(client: TestClient) -> None:
    response = client.post("/advisor/chat/stream", json={"message": "Hola"})
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"


def test_a_second_message_continues_the_conversation(client: TestClient, world: World) -> None:
    first = stream(client, {"message": "Hola"})[-1][1]
    second = stream(client, {"message": "¿Y el otro?", "thread_id": first["thread_id"]})[-1][1]
    assert second["thread_id"] == first["thread_id"]
    assert world.threads.turns[UUID(first["thread_id"])] == 2


def test_remaining_today_counts_down_with_each_message(client: TestClient) -> None:
    remaining = [stream(client, {"message": "Hola"})[-1][1]["remaining_today"] for _ in range(3)]
    assert remaining == [29, 28, 27]


def test_without_limits_remaining_today_is_null() -> None:
    with World(rate_limits_enabled=False).client() as client:
        assert stream(client, {"message": "Hola"})[-1][1]["remaining_today"] is None


# Refusals known before the turn are plain HTTP answers, never a 200 stream.


def post(client: TestClient, body: dict[str, object]) -> tuple[int, str, dict[str, Any]]:
    response = client.post("/advisor/chat/stream", json=body)
    return response.status_code, response.headers["content-type"], response.json()


@pytest.mark.parametrize(
    "body",
    [{"message": ""}, {"message": "   "}, {"message": "x" * 1001}, {"thread_id": None}],
)
def test_invalid_body_is_422(client: TestClient, world: World, body: dict[str, object]) -> None:
    status, content_type, _ = post(client, body)
    assert (status, content_type) == (422, "application/json")
    assert world.agent.messages == []
    assert world.opened == 0


def test_the_sixth_message_of_a_minute_is_429_with_retry_after(
    client: TestClient, world: World
) -> None:
    for _ in range(5):
        stream(client, {"message": "Hola"})
    response = client.post("/advisor/chat/stream", json={"message": "Una más"})
    assert response.status_code == 429
    assert response.headers["content-type"] == "application/json"
    assert int(response.headers["retry-after"]) > 0
    assert len(world.agent.messages) == 5


def test_unknown_conversation_is_404(client: TestClient, world: World) -> None:
    assert post(client, {"message": "Hola", "thread_id": str(uuid4())}) == (
        404,
        "application/json",
        {"detail": "conversation not found"},
    )
    assert world.agent.messages == []


def test_conversation_at_the_limit_is_409(client: TestClient, world: World) -> None:
    thread_id = world.threads.create()
    world.threads.turns[thread_id] = 20
    assert post(client, {"message": "Una más", "thread_id": str(thread_id)}) == (
        409,
        "application/json",
        {"detail": "conversation limit reached"},
    )
    assert world.agent.messages == []


def test_budget_exhausted_is_503_before_the_stream(client: TestClient, world: World) -> None:
    world.usage.spent = Decimal("0.20")
    assert post(client, {"message": "Hola"}) == (
        503,
        "application/json",
        {"detail": "advisor budget exhausted for today"},
    )
    assert world.agent.messages == []
    assert world.threads.turns == {}


def test_counters_down_is_503_before_the_stream(client: TestClient, world: World) -> None:
    counters = InMemoryCounters()
    counters.down = True
    world.limiter = RateLimiter(counters, world.settings, Clock())
    status, content_type, body = post(client, {"message": "Hola"})
    assert (status, content_type, body) == (
        503,
        "application/json",
        {"detail": "service unavailable"},
    )
    assert world.agent.messages == []


# Failures after the stream opened arrive as an `error` event.


def test_too_many_tool_rounds_is_an_error_event_and_the_spend_is_committed(
    client: TestClient, world: World
) -> None:
    world.agent.error = AdvisorLimitError("too many tool rounds", [CALL, CALL])
    events = stream(client, {"message": "Bucle"})
    assert [name for name, _ in events] == ["step"] * 4 + ["error"]
    assert events[-1][1] == {"status": 503, "detail": "advisor could not answer"}
    assert world.usage.rows == [CALL, CALL]
    assert world.session.commits == 1


def test_unavailable_model_is_an_error_event_without_commit(
    client: TestClient, world: World
) -> None:
    world.agent.error = AdvisorUnavailableError("OPENAI_API_KEY is not set")
    events = stream(client, {"message": "Hola"})
    assert events[-1] == ("error", {"status": 503, "detail": "advisor unavailable"})
    assert world.session.commits == 0


def test_an_unexpected_failure_is_an_error_event_and_is_logged(
    client: TestClient, world: World, caplog: pytest.LogCaptureFixture
) -> None:
    world.agent.error = RuntimeError("database went away")
    events = stream(client, {"message": "Hola"})
    assert events[-1] == ("error", {"status": 503, "detail": "advisor unavailable"})
    assert "advisor stream turn failed" in caplog.text
    # No trace reaches the client.
    assert all("database" not in json.dumps(data) for _, data in events)


def test_a_turn_too_slow_ends_the_stream_but_is_still_recorded(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(advisor_route, "TURN_TIMEOUT_SECONDS", 0.2)
    world.agent.release = threading.Event()

    events = stream(client, {"message": "Hola"})

    assert events[-1] == ("error", {"status": 503, "detail": "advisor could not answer"})
    assert list(world.threads.turns.values()) == [0]  # created, not answered yet
    # The turn goes on after the stream ended, as when the browser goes away.
    world.agent.release.set()
    for thread in threading.enumerate():
        if thread.name == "advisor-turn":
            thread.join(timeout=5)
    assert list(world.threads.turns.values()) == [1]
    assert world.usage.rows == [CALL]
    assert world.session.commits == 1
