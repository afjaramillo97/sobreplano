"""Unit tests for the AskAdvisor use case, with in-memory doubles."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from sobreplano.application.ask_advisor import AskAdvisor
from sobreplano.domain.advisor import AdvisorReply, LlmCall
from sobreplano.domain.errors import (
    AdvisorBudgetExceededError,
    AdvisorLimitError,
    AdvisorThreadNotFoundError,
    AdvisorTurnLimitError,
    AdvisorUnavailableError,
)

TODAY = date(2026, 11, 13)
CALL = LlmCall(
    model="openai:gpt-6-luna", input_tokens=1000, output_tokens=100, cost_usd=Decimal("0.01")
)


class FakeAgent:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple[UUID, str]] = []

    def reply(self, thread_id: UUID, message: str) -> AdvisorReply:
        self.calls.append((thread_id, message))
        if self.error is not None:
            raise self.error
        return AdvisorReply(text="Hola.", tools_used=["search_projects"], llm_calls=[CALL, CALL])


class InMemoryUsage:
    def __init__(self, spent_today: Decimal = Decimal(0)) -> None:
        self.spent_today = spent_today
        self.rows: list[tuple[str, LlmCall, UUID | None]] = []

    def add(self, feature: str, call: LlmCall, thread_id: UUID | None) -> None:
        self.rows.append((feature, call, thread_id))

    def cost_on(self, feature: str, day: date) -> Decimal:
        assert (feature, day) == ("advisor", TODAY)
        return self.spent_today + sum(
            (c.cost_usd or Decimal(0) for _, c, _ in self.rows), Decimal(0)
        )


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


def make(
    agent: FakeAgent | None = None,
    usage: InMemoryUsage | None = None,
    threads: InMemoryThreads | None = None,
) -> tuple[AskAdvisor, FakeAgent, InMemoryUsage, InMemoryThreads]:
    agent, usage, threads = (
        agent or FakeAgent(),
        usage or InMemoryUsage(),
        threads or InMemoryThreads(),
    )
    ask = AskAdvisor(agent, usage, threads, daily_budget_usd=Decimal("0.20"), max_turns=3)
    return ask, agent, usage, threads


def test_new_conversation_is_created_answered_and_recorded() -> None:
    ask, agent, usage, threads = make()
    answer = ask(None, "Busco en Sabaneta", TODAY)

    assert answer.reply.text == "Hola."
    assert agent.calls == [(answer.thread_id, "Busco en Sabaneta")]
    assert threads.turns == {answer.thread_id: 1}
    assert usage.rows == [("advisor", CALL, answer.thread_id)] * 2


def test_existing_conversation_continues() -> None:
    ask, _, _, threads = make()
    thread_id = ask(None, "Primera", TODAY).thread_id
    assert ask(thread_id, "Segunda", TODAY).thread_id == thread_id
    assert threads.turns[thread_id] == 2


def test_budget_spent_does_not_call_the_agent_nor_create_a_thread() -> None:
    ask, agent, usage, threads = make(usage=InMemoryUsage(spent_today=Decimal("0.20")))
    with pytest.raises(AdvisorBudgetExceededError):
        ask(None, "Hola", TODAY)
    assert agent.calls == []
    assert threads.turns == {}
    assert usage.rows == []


def test_just_under_the_budget_still_answers() -> None:
    ask, agent, _, _ = make(usage=InMemoryUsage(spent_today=Decimal("0.199999")))
    ask(None, "Hola", TODAY)
    assert len(agent.calls) == 1


def test_unknown_conversation() -> None:
    ask, agent, _, _ = make()
    with pytest.raises(AdvisorThreadNotFoundError):
        ask(uuid4(), "Hola", TODAY)
    assert agent.calls == []


def test_conversation_at_the_message_limit() -> None:
    ask, agent, _, threads = make()
    thread_id = threads.create()
    threads.turns[thread_id] = 3
    with pytest.raises(AdvisorTurnLimitError):
        ask(thread_id, "Una más", TODAY)
    assert agent.calls == []


def test_limit_error_records_the_spend_and_reraises() -> None:
    error = AdvisorLimitError("too many tool rounds", [CALL, CALL, CALL])
    ask, _, usage, threads = make(agent=FakeAgent(error))
    with pytest.raises(AdvisorLimitError):
        ask(None, "Bucle", TODAY)
    assert len(usage.rows) == 3
    [thread_id] = threads.turns
    assert all(row[2] == thread_id for row in usage.rows)
    # A message without an answer does not count toward the conversation's limit.
    assert threads.turns[thread_id] == 0


def test_unavailable_agent_propagates_without_recording() -> None:
    ask, _, usage, _ = make(agent=FakeAgent(AdvisorUnavailableError("no key")))
    with pytest.raises(AdvisorUnavailableError):
        ask(None, "Hola", TODAY)
    assert usage.rows == []
