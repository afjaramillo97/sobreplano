"""Unit tests for the advisor evals runner with a scripted model (no paid calls)."""

import json
from collections.abc import Callable, Generator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import InMemorySaver

from sobreplano.domain.advisor import LlmCall
from sobreplano.domain.listings import (
    DeveloperSummary,
    ProjectDetail,
    ProjectFilters,
    ProjectPage,
    ProjectSort,
)
from sobreplano.evals.advisor.cases import EvalCase, RubricId
from sobreplano.evals.advisor.judge import Judge, JudgeInput, JudgeOutcome, Verdict
from sobreplano.evals.advisor.runner import (
    AdvisorRunReport,
    TurnTracer,
    run_advisor_evals,
    tool_definition_numbers,
)
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
    cases: list[EvalCase],
    script: list[Callable[[], AIMessage]],
    *,
    repeat: int = 1,
    cap: str = "1",
    judge: Judge | None = None,
    calibrated: frozenset[str] = frozenset(),
    tracer: TurnTracer | None = None,
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
        judge=judge,
        calibrated=calibrated,
        tracer=tracer,
        run_id="run-test",
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


class FakeJudge:
    """Fails the rubrics it is told to, costs 0.01 USD per call and records what it saw."""

    model = "openai:gpt-6.1-terra"
    prompt_version = "judgejudge00"

    def __init__(self, failing: set[str] | None = None) -> None:
        self.failing = failing or set()
        self.seen: list[tuple[str, JudgeInput]] = []

    def judge(self, rubric: RubricId, data: JudgeInput) -> JudgeOutcome:
        self.seen.append((rubric, data))
        call = LlmCall(self.model, 100, 10, Decimal("0.01"), self.prompt_version)
        return JudgeOutcome(
            Verdict(reason=f"{rubric} reason", passed=rubric not in self.failing), call
        )


HELPFUL_CASE = SEARCH_CASE.model_copy(
    update={
        "turns": [
            SEARCH_CASE.turns[0].model_copy(
                update={
                    "expect": SEARCH_CASE.turns[0].expect.model_copy(
                        update={"rubrics": ["helpful", "scope"]}
                    )
                }
            )
        ]
    }
)


def test_judge_verdicts_are_recorded_with_their_cost() -> None:
    judge = FakeJudge()
    report = run([HELPFUL_CASE], search_turn(), judge=judge)

    [turn] = report.runs[0].turns
    assert [(r.rubric, r.passed, r.reason) for r in turn.rubrics] == [
        ("helpful", True, "helpful reason"),
        ("scope", True, "scope reason"),
    ]
    _, data = judge.seen[0]
    assert data.user_messages == ["¿Qué hay en Sabaneta?"]
    assert data.tool_results and '"total":0' in data.tool_results[0]
    assert data.answer == "No encontré proyectos."
    assert report.judge_model == judge.model
    assert (report.judge_usage.calls, report.judge_usage.cost_usd) == (2, Decimal("0.02"))
    assert report.advisor_usage.calls == 2


def test_only_calibrated_rubrics_block() -> None:
    judge = FakeJudge(failing={"helpful", "scope"})
    report = run([HELPFUL_CASE], search_turn(), judge=judge, calibrated=frozenset({"scope"}))

    rates = {r.name: r for r in report.rubric_rates()}
    assert not rates["helpful"].blocking and rates["helpful"].ok
    assert rates["scope"].blocking and not rates["scope"].ok
    assert report.failures() == ["scope 0.0 % < 85%"]
    assert not report.runs[0].passed
    markdown = report.to_markdown()
    assert "| helpful | 0/1 | 0.0 % | not calibrated | 0 | report only |" in markdown
    assert "rubric `helpful` (report only): helpful reason" in markdown


def test_uncalibrated_failing_rubric_does_not_fail_the_case() -> None:
    report = run([HELPFUL_CASE], search_turn(), judge=FakeJudge(failing={"helpful"}))
    assert report.runs[0].passed
    assert report.failures() == []


def test_judge_cost_counts_toward_the_cap() -> None:
    # The advisor costs 0.0003 per case and the judge 0.02: the cap stops the second case.
    report = run(
        [HELPFUL_CASE, SEARCH_CASE], [*search_turn(), *search_turn()], cap="0.01", judge=FakeJudge()
    )
    assert not report.complete
    assert [r.case_id for r in report.runs] == ["S9"]


def test_turn_that_did_not_complete_is_not_judged() -> None:
    judge = FakeJudge()
    script = [tool_call("search_projects", municipality="sabaneta") for _ in range(6)]
    report = run([HELPFUL_CASE], script, judge=judge)
    assert report.runs[0].turns[0].rubrics == []
    assert judge.seen == []


class FakeTracer:
    """Records the turns it opened and the scores it got, like Langfuse would."""

    def __init__(self) -> None:
        self.turns: list[dict[str, Any]] = []
        self.scores: list[tuple[str | None, str, bool]] = []

    @contextmanager
    def turn(
        self, *, case_id: str, run: int, turn: int, message: str, session_id: str
    ) -> Generator[str | None]:
        self.turns.append({"case_id": case_id, "run": run, "turn": turn, "session_id": session_id})
        yield f"trace-{case_id}-{turn}"

    def score(self, trace_id: str | None, name: str, passed: bool, comment: str) -> None:
        self.scores.append((trace_id, name, passed))


def test_each_turn_is_traced_and_scored_by_its_checks_and_rubrics() -> None:
    tracer = FakeTracer()
    report = run([HELPFUL_CASE], search_turn(), judge=FakeJudge(failing={"scope"}), tracer=tracer)

    [turn] = report.runs[0].turns
    assert turn.trace_id == "trace-S9-1"
    assert tracer.turns == [
        {"case_id": "S9", "run": 1, "turn": 1, "session_id": report.runs[0].thread_id}
    ]
    names = {name: passed for _, name, passed in tracer.scores}
    assert names["check.completed"] and names["check.tools"]
    assert names["rubric.helpful"] and not names["rubric.scope"]
    assert {trace_id for trace_id, _, _ in tracer.scores} == {"trace-S9-1"}
    assert report.run_id == "run-test"


def test_tool_definition_numbers_keep_limits_and_drop_examples() -> None:
    numbers = set(tool_definition_numbers(build_tools(EmptyQuery())))
    # 30 % default down payment, 5 to 30 years, payment at most 40 % of income.
    assert {Decimal(30), Decimal(5), Decimal(40)} <= numbers
    # "e.g. 12 for 12 %" is only an example of a rate.
    assert Decimal(12) not in numbers
