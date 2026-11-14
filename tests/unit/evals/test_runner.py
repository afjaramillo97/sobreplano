"""Unit tests for the advisor evals runner with a scripted model (no paid calls)."""

import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import InMemorySaver

from sobreplano.domain.listings import (
    DeveloperSummary,
    ProjectDetail,
    ProjectFilters,
    ProjectPage,
    ProjectSort,
)
from sobreplano.evals.advisor.cases import EvalCase
from sobreplano.evals.advisor.runner import AdvisorRunReport, run_advisor_evals
from sobreplano.evals.report import CostCap, report_stem, write_report
from sobreplano.infrastructure.advisor.langgraph_advisor import LangGraphAdvisor
from sobreplano.infrastructure.advisor.tools import build_tools

MODEL = "openai:gpt-6-luna"  # priced: 1000 in + 100 out tokens cost 0.00015 USD per call
USAGE = {"input_tokens": 1000, "output_tokens": 100, "total_tokens": 1100}
NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)


class ScriptedChatModel(BaseChatModel):
    """Answers with the next scripted message (a factory: ids are assigned in place)."""

    script: list[Callable[[], AIMessage]]

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=self.script.pop(0)())])

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> "ScriptedChatModel":  # type: ignore[override]
        return self


def answer(text: str) -> Callable[[], AIMessage]:
    return lambda: AIMessage(content=text, usage_metadata=USAGE)  # type: ignore[arg-type]


def tool_call(name: str, **args: Any) -> Callable[[], AIMessage]:
    return lambda: AIMessage(
        content="",
        tool_calls=[{"id": f"call-{uuid4().hex[:8]}", "name": name, "args": args}],
        usage_metadata=USAGE,  # type: ignore[arg-type]
    )


class EmptyQuery:
    def list_projects(
        self, *, filters: ProjectFilters, sort: ProjectSort, limit: int, offset: int
    ) -> ProjectPage:
        return ProjectPage(items=[], total=0)

    def get_project(self, slug: str) -> ProjectDetail | None:
        return None

    def list_developers(self) -> list[DeveloperSummary]:
        return []


SEARCH_CASE = EvalCase.model_validate(
    {
        "id": "S9",
        "category": "search",
        "description": "busca en Sabaneta",
        "turns": [
            {
                "message": "¿Qué hay en Sabaneta?",
                "expect": {
                    "tools_required": ["search_projects"],
                    "tool_args": {"search_projects": {"municipality": {"eq": "sabaneta"}}},
                },
            }
        ],
    }
)
DEVELOPERS_CASE = EvalCase.model_validate(
    {
        "id": "S8",
        "category": "search",
        "description": "lista constructoras",
        "turns": [
            {
                "message": "¿Qué constructoras hay?",
                "expect": {"tools_required": ["list_developers"]},
            }
        ],
    }
)


def run(
    cases: list[EvalCase], script: list[Callable[[], AIMessage]], *, repeat: int = 1, cap: str = "1"
) -> AdvisorRunReport:
    model = ScriptedChatModel(script=script)
    advisor = LangGraphAdvisor(
        chat_model=lambda: model,
        model_name=MODEL,
        tools=build_tools(EmptyQuery()),
        checkpointer=InMemorySaver(),
    )
    return run_advisor_evals(
        cases,
        advisor,
        model=MODEL,
        prompt_versions={"advisor_system": "abc"},
        commit="deadbee",
        repeat=repeat,
        cost_cap=CostCap(Decimal(cap)),
        now=lambda: NOW,
    )


def search_turn() -> list[Callable[[], AIMessage]]:
    return [tool_call("search_projects", municipality="sabaneta"), answer("No encontré proyectos.")]


def test_passing_case_and_case_that_fails_tools() -> None:
    # The developers case searches instead of listing developers.
    report = run([SEARCH_CASE, DEVELOPERS_CASE], [*search_turn(), *search_turn()])

    assert report.complete
    passed, failed = report.runs
    assert passed.passed and passed.turns[0].trace.tool_calls[0].args == {
        "municipality": "sabaneta"
    }
    assert not failed.passed
    [tools] = [c for c in failed.turns[0].checks if c.name == "tools"]
    assert not tools.passed and "missing ['list_developers']" in tools.detail

    rates = {rate.name: (rate.passed, rate.total) for rate in report.check_rates()}
    assert rates["tools"] == (1, 2)
    assert rates["completed"] == (2, 2)
    assert report.failures() == ["tools 50.0 % < 90%"]
    assert report.advisor_usage.calls == 4
    assert report.advisor_usage.cost_usd == Decimal("0.000600")


def test_cost_cap_stops_before_the_next_case_and_marks_the_run_incomplete() -> None:
    # Each case costs 0.0003 USD: the cap is passed after the first one.
    report = run([SEARCH_CASE, DEVELOPERS_CASE], search_turn(), cap="0.0002")

    assert not report.complete
    assert [r.case_id for r in report.runs] == ["S9"]
    assert report.stop_reason is not None and "before S8 run 1" in report.stop_reason
    assert report.failures()[0].startswith("incomplete")


def test_repeat_reports_consistency() -> None:
    script = [*search_turn(), tool_call("list_developers"), answer("Ninguna."), *search_turn()]
    script += [*search_turn()]  # second run: the developers case searches instead
    report = run([SEARCH_CASE, DEVELOPERS_CASE], script, repeat=2)

    assert [(r.case_id, r.run, r.passed) for r in report.runs] == [
        ("S9", 1, True),
        ("S8", 1, True),
        ("S9", 2, True),
        ("S8", 2, False),
    ]
    assert report.consistency() == (["S9"], ["S8"])


def test_limit_error_is_a_failed_turn_with_its_calls() -> None:
    script = [tool_call("search_projects", municipality="sabaneta") for _ in range(6)]
    report = run([SEARCH_CASE], script)

    [turn] = report.runs[0].turns
    assert [(c.name, c.passed) for c in turn.checks] == [("completed", False)]
    assert turn.trace.error is not None and "AdvisorLimitError" in turn.trace.error
    assert report.advisor_usage.calls == 6


def test_report_round_trips_through_json_and_renders_markdown(tmp_path: Path) -> None:
    report = run([SEARCH_CASE, DEVELOPERS_CASE], [*search_turn(), *search_turn()])

    path = write_report(
        report_stem("advisor", MODEL, NOW.date()),
        report.model_dump_json(),
        report.to_markdown(),
        tmp_path,
    )

    assert path.name == "advisor-2026-11-13-openai_gpt-6-luna.json"
    assert AdvisorRunReport.model_validate_json(path.read_text()) == report
    assert (
        json.loads(path.read_text())["runs"][0]["turns"][0]["trace"]["tool_calls"][0]["name"]
        == "search_projects"
    )
    markdown = path.with_suffix(".md").read_text()
    assert "**FAIL**" in markdown
    assert "| tools | 1/2 | 50.0 % | 90% | **fail** |" in markdown
    assert "**S8** run 1 turn 1" in markdown
