"""Contract of POST /advisor/chat with in-memory doubles: no database, no model, no mocks."""

from collections.abc import Iterator
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from sobreplano.application.ask_advisor import AskAdvisor
from sobreplano.domain.advisor import AdvisorReply, LlmCall
from sobreplano.domain.errors import AdvisorLimitError, AdvisorUnavailableError
from sobreplano.infrastructure.settings import Settings
from sobreplano.interface.api.dependencies import get_ask_advisor, get_session
from sobreplano.interface.api.main import create_app

CALL = LlmCall(model="openai:gpt-6-luna", input_tokens=10, output_tokens=5, cost_usd=Decimal(1))


class FakeAgent:
    def __init__(self) -> None:
        self.error: Exception | None = None
        self.messages: list[str] = []

    def reply(self, thread_id: UUID, message: str) -> AdvisorReply:
        self.messages.append(message)
        if self.error is not None:
            raise self.error
        return AdvisorReply(
            text="Encontré 2 proyectos.", tools_used=["search_projects"], llm_calls=[CALL]
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
    """Counts commits: the route is the one that commits."""

    def __init__(self) -> None:
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1


class World:
    def __init__(self) -> None:
        self.agent = FakeAgent()
        self.usage = InMemoryUsage()
        self.threads = InMemoryThreads()
        self.session = FakeSession()
        self.ask = AskAdvisor(
            self.agent, self.usage, self.threads, daily_budget_usd=Decimal("0.20"), max_turns=20
        )


@pytest.fixture
def world() -> World:
    return World()


@pytest.fixture
def client(world: World) -> Iterator[TestClient]:
    app = create_app(Settings(database_url="postgresql+psycopg://unused@127.0.0.1:1/unused"))
    app.dependency_overrides[get_ask_advisor] = lambda: world.ask
    app.dependency_overrides[get_session] = lambda: world.session
    with TestClient(app) as client:
        yield client


def post(client: TestClient, body: dict[str, object]) -> tuple[int, dict[str, object]]:
    response = client.post("/advisor/chat", json=body)
    return response.status_code, response.json()


def test_new_conversation_matches_the_contract(client: TestClient, world: World) -> None:
    status, body = post(client, {"message": "Busco 3 alcobas en Sabaneta", "thread_id": None})

    assert status == 200
    assert body["reply"] == "Encontré 2 proyectos."
    assert body["tools_used"] == ["search_projects"]
    assert UUID(str(body["thread_id"])) in world.threads.turns
    assert world.session.commits == 1
    assert world.usage.rows == [CALL]


def test_existing_conversation_continues(client: TestClient, world: World) -> None:
    _, first = post(client, {"message": "Hola"})
    status, second = post(client, {"message": "¿Y el primero?", "thread_id": first["thread_id"]})
    assert status == 200
    assert second["thread_id"] == first["thread_id"]


@pytest.mark.parametrize(
    "body",
    [
        {"message": ""},
        {"message": "   "},
        {"message": "x" * 1001},
        {"message": "Hola", "thread_id": "not-a-uuid"},
        {},
    ],
)
def test_invalid_body_is_422(client: TestClient, world: World, body: dict[str, object]) -> None:
    status, _ = post(client, body)
    assert status == 422
    assert world.agent.messages == []


def test_message_of_exactly_1000_characters_is_accepted(client: TestClient) -> None:
    status, _ = post(client, {"message": "x" * 1000})
    assert status == 200


def test_unknown_conversation_is_404(client: TestClient) -> None:
    assert post(client, {"message": "Hola", "thread_id": str(uuid4())}) == (
        404,
        {"detail": "conversation not found"},
    )


def test_conversation_at_the_limit_is_409(client: TestClient, world: World) -> None:
    thread_id = world.threads.create()
    world.threads.turns[thread_id] = 20
    assert post(client, {"message": "Una más", "thread_id": str(thread_id)}) == (
        409,
        {"detail": "conversation limit reached"},
    )


def test_budget_exhausted_is_503_without_calling_the_model(
    client: TestClient, world: World
) -> None:
    world.usage.spent = Decimal("0.20")
    assert post(client, {"message": "Hola"}) == (
        503,
        {"detail": "advisor budget exhausted for today"},
    )
    assert world.agent.messages == []
    assert world.usage.rows == []


def test_unavailable_model_is_503(client: TestClient, world: World) -> None:
    world.agent.error = AdvisorUnavailableError("OPENAI_API_KEY is not set")
    assert post(client, {"message": "Hola"}) == (503, {"detail": "advisor unavailable"})
    assert world.session.commits == 0


def test_too_many_tool_rounds_is_503_and_the_spend_is_committed(
    client: TestClient, world: World
) -> None:
    world.agent.error = AdvisorLimitError("too many tool rounds", [CALL, CALL])
    assert post(client, {"message": "Bucle"}) == (503, {"detail": "advisor could not answer"})
    assert world.usage.rows == [CALL, CALL]
    assert world.session.commits == 1
