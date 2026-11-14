"""Unit tests for the deterministic checks, over hand-made traces (no LLM)."""

import json
from typing import Any

import pytest

from sobreplano.domain.advisor import ToolCallRecord
from sobreplano.evals.advisor.cases import ArgExpectation, TurnExpectation, load_cases
from sobreplano.evals.advisor.checks import (
    TurnTrace,
    arg_matches,
    check_cites_source,
    check_completed,
    check_grounded,
    check_language,
    check_mentions,
    check_tool_args,
    check_tools,
    run_checks,
)

URL = "https://example.com/proyectos/mirador-del-ejemplo"
SEARCH_OUTPUT = json.dumps(
    {
        "total": 1,
        "projects": [
            {
                "slug": "mirador-del-ejemplo",
                "name": "Mirador del Ejemplo",
                "source_url": URL,
                "unit_types": [
                    {
                        "name": "Tipo B",
                        "latest_price_cop": 445000000,
                        "change_since_first_pct": 8.54,
                    }
                ],
            }
        ],
    },
    separators=(",", ":"),
)


def call(name: str, output: str = "{}", **args: Any) -> ToolCallRecord:
    return ToolCallRecord(name=name, args=args, output=output)


def trace(
    answer: str, *calls: ToolCallRecord, message: str = "Hola", error: str | None = None
) -> TurnTrace:
    return TurnTrace(
        message=message, answer=answer, tool_calls=list(calls), llm_calls=[], error=error
    )


def expect(**fields: Any) -> TurnExpectation:
    return TurnExpectation.model_validate(fields)


# completed


def test_completed_needs_no_error_and_an_answer() -> None:
    assert check_completed(trace("Listo.")).passed
    assert not check_completed(trace("", error="AdvisorLimitError: too many tool rounds")).passed
    assert check_completed(trace("   ")).detail == "empty answer"


# tools


def test_required_tools_with_repeats() -> None:
    turn = trace("x", call("search_projects"), call("get_project"), call("search_projects"))
    assert check_tools(expect(tools_required=["search_projects", "search_projects"]), turn).passed
    result = check_tools(expect(tools_required=["get_project", "get_project"]), turn)
    assert not result.passed and "missing ['get_project']" in result.detail


def test_ordered_tools() -> None:
    wanted = expect(tools_required=["search_projects", "get_project"], tools_ordered=True)
    assert check_tools(wanted, trace("x", call("search_projects"), call("get_project"))).passed
    assert check_tools(
        wanted, trace("x", call("get_project"), call("search_projects"), call("get_project"))
    ).passed
    assert not check_tools(wanted, trace("x", call("get_project"), call("search_projects"))).passed


def test_forbidden_tool() -> None:
    result = check_tools(
        expect(tools_forbidden=["simulate_mortgage"]), trace("x", call("simulate_mortgage"))
    )
    assert not result.passed and "forbidden" in result.detail
    assert check_tools(expect(tools_forbidden=["simulate_mortgage"]), trace("¿Qué tasa?")).passed


# tool_args


def test_one_call_must_meet_every_expectation() -> None:
    wanted = expect(
        tool_args={
            "search_projects": {
                "municipality": {"eq": "sabaneta"},
                "max_price": {"lte": 450000000},
            }
        }
    )
    # Each call meets one expectation, none meets both.
    split = trace(
        "x",
        call("search_projects", municipality="sabaneta"),
        call("search_projects", max_price=400000000),
    )
    assert not check_tool_args(wanted, split).passed
    both = trace("x", call("search_projects", municipality="Sabaneta", max_price=450000000))
    assert check_tool_args(wanted, both).passed


def test_missing_tool_fails_tool_args() -> None:
    wanted = expect(tool_args={"get_project": {"slug": {"eq": "parque-ficticio"}}})
    assert not check_tool_args(wanted, trace("x", call("search_projects"))).passed


@pytest.mark.parametrize(
    ("expectation", "value", "passed"),
    [
        ({"eq": 12}, 12.0, True),
        ({"eq": 12}, 12.5, False),
        ({"eq": 12}, True, False),
        ({"eq": "itagui"}, "Itagüí", True),
        ({"eq": "itagui"}, 1, False),
        ({"lte": 450000000}, 450000000, True),
        ({"lte": 450000000}, 450000001, False),
        ({"lte": 450000000}, "450000000", False),
        ({"gte": 80}, 80, True),
        ({"gte": 80}, 79.9, False),
        (
            {"contains": ["mirador-del-ejemplo", "torres-demo"]},
            ["torres-demo", "mirador-del-ejemplo"],
            True,
        ),
        ({"contains": ["mirador-del-ejemplo", "torres-demo"]}, ["torres-demo"], False),
        ({"contains": ["parque"]}, "Parque Ficticio", True),
        ({"contains": ["parque"]}, 3, False),
    ],
)
def test_arg_matches(expectation: dict[str, Any], value: object, passed: bool) -> None:
    assert arg_matches(ArgExpectation.model_validate(expectation), value) is passed


def test_empty_arg_expectation_is_rejected() -> None:
    with pytest.raises(ValueError, match="needs eq"):
        ArgExpectation()


# mentions


def test_mentions_ignore_accents_and_case() -> None:
    wanted = expect(must_mention=["Jardín de Prueba", "30 años"], must_not_mention=["Torres Demo"])
    assert check_mentions(wanted, trace("JARDIN DE PRUEBA; el plazo máximo es 30 anos.")).passed
    result = check_mentions(wanted, trace("Torres Demo y Jardín de Prueba"))
    assert not result.passed
    assert "missing ['30 años']" in result.detail
    assert "should not mention ['Torres Demo']" in result.detail


# grounded


def test_figures_from_tool_results_are_grounded() -> None:
    turn = trace(
        "Tipo B: $445.000.000, subió 8,54 %.",
        call("search_projects", SEARCH_OUTPUT),
    )
    assert check_grounded(turn, []).passed


def test_rounded_figure_within_half_a_percent_is_grounded() -> None:
    # 445 millones vs 446.000.000 differs by 0.22 %.
    turn = trace("Unos 445 millones.", call("x", '{"price_cop":446000000}'))
    assert check_grounded(turn, []).passed


def test_invented_figure_is_not_grounded() -> None:
    turn = trace(
        "Tipo B: $445.000.000; Tipo D: $470.000.000.", call("search_projects", SEARCH_OUTPUT)
    )
    result = check_grounded(turn, [])
    assert not result.passed
    assert "470.000.000" in result.detail and "445.000.000" not in result.detail


def test_figures_from_user_messages_and_earlier_turns_are_grounded() -> None:
    earlier = trace("…", call("search_projects", SEARCH_OUTPUT), message="Busco en Sabaneta")
    turn = trace("Con 12 % EA, el tipo B de 445 millones…", message="¿Y al 12 %?")
    assert check_grounded(turn, [earlier]).passed


def test_answer_without_figures_is_grounded() -> None:
    assert check_grounded(trace("¿Qué tasa de interés te ofrece el banco?"), []).passed


# cites_source


def test_project_price_with_source_url_cites() -> None:
    turn = trace(f"Tipo B desde $445.000.000 ({URL}).", call("search_projects", SEARCH_OUTPUT))
    result = check_cites_source(turn, [])
    assert result is not None and result.passed


def test_project_price_without_source_url_does_not_cite() -> None:
    turn = trace("Tipo B desde $445.000.000.", call("search_projects", SEARCH_OUTPUT))
    result = check_cites_source(turn, [])
    assert result is not None and not result.passed


def test_cites_source_does_not_apply_without_a_project_price() -> None:
    mortgage = call("simulate_mortgage", '{"monthly_payment_cop":2964145}')
    assert check_cites_source(trace("Cuota: $2.964.145.", mortgage), []) is None
    assert check_cites_source(trace("Hola."), []) is None


def test_cites_source_uses_tool_results_of_earlier_turns() -> None:
    earlier = trace("…", call("search_projects", SEARCH_OUTPUT))
    result = check_cites_source(trace("El tipo B cuesta $445.000.000."), [earlier])
    assert result is not None and not result.passed


# language


def test_language() -> None:
    assert check_language(expect(language="en"), trace("There are 2 projects in Envigado.")).passed
    assert not check_language(expect(language="en"), trace("Hay 2 proyectos en Envigado.")).passed


# run_checks


def test_run_checks_only_runs_what_the_turn_asks_for() -> None:
    turn = trace("Hola, ¿en qué municipio buscas?")
    assert [r.name for r in run_checks(expect(), turn, [])] == ["completed", "grounded", "language"]


def test_run_checks_runs_every_check_that_applies() -> None:
    wanted = expect(
        tools_required=["search_projects"],
        tool_args={"search_projects": {"municipality": {"eq": "sabaneta"}}},
        must_mention=["Mirador del Ejemplo"],
    )
    turn = trace(
        f"Mirador del Ejemplo, tipo B desde $445.000.000: {URL}",
        call("search_projects", SEARCH_OUTPUT, municipality="sabaneta"),
    )
    results = run_checks(wanted, turn, [])
    assert [r.name for r in results] == [
        "completed",
        "tools",
        "tool_args",
        "mentions",
        "grounded",
        "cites_source",
        "language",
    ]
    assert all(r.passed for r in results)


def test_turn_that_did_not_complete_only_reports_completed() -> None:
    results = run_checks(expect(tools_required=["x"]), trace("", error="limit"), [])
    assert [(r.name, r.passed) for r in results] == [("completed", False)]


# case file


def test_case_file_has_the_24_cases_of_the_spec() -> None:
    cases = load_cases()
    assert len(cases) == 24
    assert {case.id for case in cases if len(case.turns) == 2} == {"H1", "M1", "M2"}
    by_category = {
        category: 0 for category in ["search", "history", "compare", "finance", "scope", "memory"]
    }
    for case in cases:
        by_category[case.category] += 1
    assert by_category == {
        "search": 7,
        "history": 3,
        "compare": 2,
        "finance": 6,
        "scope": 4,
        "memory": 2,
    }


def test_case_tools_exist() -> None:
    known = {
        "search_projects",
        "get_project",
        "compare_projects",
        "list_developers",
        "simulate_mortgage",
        "max_affordable_price",
        "down_payment_plan",
    }
    for case in load_cases():
        for turn in case.turns:
            named = {
                *turn.expect.tools_required,
                *turn.expect.tools_forbidden,
                *turn.expect.tool_args,
            }
            assert named <= known, case.id
