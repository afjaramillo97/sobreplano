"""Integration tests: the advisor's memory lives in Postgres and survives an API restart."""

from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field
from sqlalchemy import Engine, text

from sobreplano.domain.listings import (
    DeveloperSummary,
    ProjectDetail,
    ProjectFilters,
    ProjectPage,
    ProjectSort,
)
from sobreplano.infrastructure.advisor.checkpointer import open_checkpointer
from sobreplano.infrastructure.advisor.langgraph_advisor import LangGraphAdvisor
from sobreplano.infrastructure.advisor.tools import build_tools
from sobreplano.infrastructure.db.engine import get_database_url
from sobreplano.interface.cli import advisor_cleanup

pytestmark = pytest.mark.integration


class RecordingChatModel(BaseChatModel):
    """Answers "ok" and records the messages it was sent."""

    seen: list[list[BaseMessage]] = Field(default_factory=list[list[BaseMessage]])

    @property
    def _llm_type(self) -> str:
        return "recording"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.seen.append(list(messages))
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="ok"))])

    def bind_tools(self, tools: Any, **kwargs: Any) -> "RecordingChatModel":  # type: ignore[override]
        return self


class EmptyQuery:
    def list_projects(
        self, *, filters: ProjectFilters, sort: ProjectSort, limit: int, offset: int
    ) -> ProjectPage:
        return ProjectPage(items=[], total=0)

    def get_project(self, slug: str) -> ProjectDetail | None:
        return None

    def list_developers(self) -> list[DeveloperSummary]:
        return []


@pytest.fixture
def thread_id() -> Iterator[UUID]:
    """A fresh thread whose checkpoints are deleted at the end (the saver autocommits)."""
    thread = uuid4()
    yield thread
    with open_checkpointer(get_database_url()) as saver:
        saver.delete_thread(str(thread))


def ask_once(model: RecordingChatModel, thread: UUID, message: str) -> None:
    # A new connection and a new compiled graph each time, as two API processes would have.
    with open_checkpointer(get_database_url()) as saver:
        LangGraphAdvisor(
            lambda: model, "openai:gpt-6-luna", build_tools(EmptyQuery()), saver
        ).reply(thread, message)


def test_two_graphs_share_the_memory_of_a_thread(thread_id: UUID) -> None:
    model = RecordingChatModel()
    ask_once(model, thread_id, "Busco en Envigado")
    ask_once(model, thread_id, "¿Y en Sabaneta?")

    texts = [message.text for message in model.seen[-1]]
    assert "Busco en Envigado" in texts
    assert texts[-1] == "¿Y en Sabaneta?"


def test_checkpoints_are_written_and_deleted(engine: Engine, thread_id: UUID) -> None:
    ask_once(RecordingChatModel(), thread_id, "Hola")
    with engine.connect() as connection:
        count = connection.scalar(
            text("SELECT count(*) FROM checkpoints WHERE thread_id = :t"), {"t": str(thread_id)}
        )
    assert count and count > 0
    with open_checkpointer(get_database_url()) as saver:
        saver.delete_thread(str(thread_id))
    with engine.connect() as connection:
        count = connection.scalar(
            text("SELECT count(*) FROM checkpoints WHERE thread_id = :t"), {"t": str(thread_id)}
        )
    assert count == 0


def test_cleanup_dry_run_counts(capsys: pytest.CaptureFixture[str]) -> None:
    assert advisor_cleanup.main(["--dry-run"]) == 0
    assert "conversations inactive since" in capsys.readouterr().out
