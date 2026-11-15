"""Unit tests for the numbers an advisor answer may quote: thread and tool definitions."""

from decimal import Decimal

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from sobreplano.domain.listings import (
    DeveloperSummary,
    ProjectDetail,
    ProjectFilters,
    ProjectPage,
    ProjectSort,
)
from sobreplano.infrastructure.advisor.grounding import (
    thread_source_numbers,
    tool_definition_numbers,
)
from sobreplano.infrastructure.advisor.tools import build_tools


class EmptyQuery:
    def list_projects(
        self, *, filters: ProjectFilters, sort: ProjectSort, limit: int, offset: int
    ) -> ProjectPage:
        return ProjectPage(items=[], total=0)

    def get_project(self, slug: str) -> ProjectDetail | None:
        return None

    def list_developers(self) -> list[DeveloperSummary]:
        return []


def test_tool_definition_numbers_keep_limits_and_drop_examples() -> None:
    numbers = set(tool_definition_numbers(build_tools(EmptyQuery())))
    # 30 % default down payment, 5 to 30 years, payment at most 40 % of income.
    assert {Decimal(30), Decimal(5), Decimal(40)} <= numbers
    # "e.g. 12 for 12 %" is only an example of a rate.
    assert Decimal(12) not in numbers


def test_thread_sources_are_user_messages_tool_results_and_arguments() -> None:
    call = {"id": "c1", "name": "simulate_mortgage", "args": {"annual_rate_ea_pct": 12.5}}
    messages = [
        HumanMessage("Gano 6 millones"),
        AIMessage(content="", tool_calls=[call]),
        ToolMessage(content='{"monthly_payment_cop": 3050000}', tool_call_id="c1"),
        AIMessage(content="Tu cuota sería de 999 millones."),
    ]
    numbers = thread_source_numbers(messages)
    assert {Decimal(6_000_000), Decimal("12.5"), Decimal(3_050_000)} <= set(numbers)
    # The advisor's own answers never ground a later figure.
    assert Decimal(999_000_000) not in numbers


def test_boolean_arguments_are_not_numbers() -> None:
    call = {"id": "c1", "name": "search_projects", "args": {"only_active": True, "limit": 5}}
    assert thread_source_numbers([AIMessage(content="", tool_calls=[call])]) == [Decimal(5)]
