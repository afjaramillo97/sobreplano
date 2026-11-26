"""Integration: a turn through POST /advisor/chat/stream leaves its conversation in Postgres."""

import json
from collections.abc import Callable, Generator, Iterator
from contextlib import contextmanager
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from sobreplano.application.ask_advisor import AskAdvisor
from sobreplano.domain.advisor import AdvisorReply, AdvisorStep, LlmCall
from sobreplano.infrastructure.db.advisor_thread_repository import SqlAdvisorThreadRepository
from sobreplano.infrastructure.db.llm_usage_repository import SqlLlmUsageRepository
from sobreplano.infrastructure.db.models import LlmUsageRow
from sobreplano.infrastructure.settings import load_settings
from sobreplano.interface.api.dependencies import get_advisor_opener
from sobreplano.interface.api.main import create_app
from sobreplano.interface.api.rate_limit import limit_advisor

pytestmark = pytest.mark.integration

CALL = LlmCall(
    model="openai:gpt-6-luna",
    input_tokens=100,
    output_tokens=10,
    cost_usd=Decimal("0.000015"),
    prompt_version="cd741d6427ec",
)


class FakeAgent:
    """Tells one tool and answers, without a model."""

    def reply(
        self,
        thread_id: UUID,
        message: str,
        on_step: Callable[[AdvisorStep], None] | None = None,
    ) -> AdvisorReply:
        if on_step is not None:
            on_step(AdvisorStep(tool="search_projects", phase="start"))
            on_step(AdvisorStep(tool="search_projects", phase="end"))
        return AdvisorReply(
            text="No encontré proyectos.",
            tools_used=["search_projects"],
            llm_calls=[CALL],
            tool_calls=[],
        )


@pytest.fixture
def stream_client(session: Session) -> Iterator[TestClient]:
    """API client whose streamed turns run on the test's rolled-back session."""
    app = create_app(load_settings())

    @contextmanager
    def open_advisor() -> Generator[tuple[AskAdvisor, Session]]:
        # A large budget: real local runs may already have spent today's.
        ask = AskAdvisor(
            FakeAgent(),
            SqlLlmUsageRepository(session),
            SqlAdvisorThreadRepository(session),
            daily_budget_usd=Decimal(1000),
            max_turns=20,
        )
        yield ask, session

    app.dependency_overrides[get_advisor_opener] = lambda: open_advisor
    # The counters commit on their own connection; test_rate_limit_repository.py covers them.
    app.dependency_overrides[limit_advisor] = lambda: None
    with TestClient(app) as client:
        yield client


def answer_of(client: TestClient, body: dict[str, object]) -> dict[str, Any]:
    response = client.post("/advisor/chat/stream", json=body)
    assert response.status_code == 200
    last = response.text.strip().split("\n\n")[-1].splitlines()
    assert last[0] == "event: answer"
    return json.loads(last[1].removeprefix("data: "))


def test_a_streamed_turn_leaves_the_conversation_and_its_spend(
    stream_client: TestClient, session: Session
) -> None:
    first = answer_of(stream_client, {"message": "Busco en Sabaneta"})
    thread_id = UUID(first["thread_id"])
    answer_of(stream_client, {"message": "¿Y en Envigado?", "thread_id": str(thread_id)})

    assert SqlAdvisorThreadRepository(session).get_turns(thread_id) == 2
    rows = session.query(LlmUsageRow).filter_by(thread_id=thread_id).all()
    assert [(row.feature, row.input_tokens) for row in rows] == [("advisor", 100)] * 2


def test_an_unknown_conversation_in_the_database_is_404(stream_client: TestClient) -> None:
    response = stream_client.post(
        "/advisor/chat/stream", json={"message": "Hola", "thread_id": str(uuid4())}
    )
    assert response.status_code == 404


def test_the_opener_gives_the_advisor_a_session_and_a_checkpointer_of_its_own() -> None:
    app = create_app(load_settings())
    with TestClient(app):  # runs the lifespan, which builds the session factory
        open_advisor = get_advisor_opener(Request({"type": "http", "app": app}))
        with open_advisor() as (ask, session):
            assert session.execute(text("SELECT 1")).scalar_one() == 1
            assert ask.threads.get_turns(uuid4()) is None
