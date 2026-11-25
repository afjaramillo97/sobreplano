"""Unit tests for the advisor's live steps and mentioned projects, with a scripted model."""

from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver
from test_advisor_tools import FakeQuery, make_detail, make_unit, point
from test_langgraph_advisor import (
    MODEL,
    ScriptedChatModel,
    answer,
    make_advisor,
    tool_call,
)

from sobreplano.domain.advisor import AdvisorStep
from sobreplano.infrastructure.advisor.langgraph_advisor import LangGraphAdvisor
from sobreplano.infrastructure.advisor.tools import build_tools


def two_tools_then_answer() -> ScriptedChatModel:
    return ScriptedChatModel(
        script=[
            tool_call("search_projects", municipality="sabaneta"),
            tool_call("list_developers"),
            answer("No encontré proyectos."),
        ]
    )


def test_each_tool_reports_start_and_end_in_order() -> None:
    steps: list[AdvisorStep] = []
    make_advisor(two_tools_then_answer()).reply(uuid4(), "¿Qué hay?", steps.append)
    assert steps == [
        AdvisorStep(tool="search_projects", phase="start"),
        AdvisorStep(tool="search_projects", phase="end"),
        AdvisorStep(tool="list_developers", phase="start"),
        AdvisorStep(tool="list_developers", phase="end"),
    ]


def test_the_reply_is_the_same_with_or_without_on_step() -> None:
    without = make_advisor(two_tools_then_answer()).reply(uuid4(), "¿Qué hay?")
    steps: list[AdvisorStep] = []
    with_steps = make_advisor(two_tools_then_answer()).reply(uuid4(), "¿Qué hay?", steps.append)
    assert with_steps == without
    assert steps


def test_a_tool_with_bad_arguments_still_ends() -> None:
    model = ScriptedChatModel(
        script=[tool_call("search_projects", min_price="mucho"), answer("No pude buscar.")]
    )
    steps: list[AdvisorStep] = []
    make_advisor(model).reply(uuid4(), "¿Qué hay?", steps.append)
    assert [step.phase for step in steps] == ["start", "end"]


def test_a_failing_on_step_does_not_stop_the_turn() -> None:
    def broken(step: AdvisorStep) -> None:
        raise RuntimeError("the queue is gone")

    reply = make_advisor(two_tools_then_answer()).reply(uuid4(), "¿Qué hay?", broken)
    assert reply.text == "No encontré proyectos."


def test_the_reply_lists_the_projects_its_text_names() -> None:
    query = FakeQuery(
        [
            make_detail("arrayanes-del-sur", "Arrayanes del Sur", [make_unit("A", [point(1, 1)])]),
            make_detail("cipres", "Ciprés", [make_unit("A", [point(1, 1)])]),
        ]
    )
    model = ScriptedChatModel(
        script=[
            tool_call("get_project", slug="arrayanes-del-sur"),
            tool_call("get_project", slug="cipres"),
            answer("Te sirve CIPRES; Arrayanes del Sur queda más lejos."),
        ]
    )
    advisor = LangGraphAdvisor(
        chat_model=lambda: model,
        model_name=MODEL,
        tools=lambda: build_tools(query),
        checkpointer=InMemorySaver(),
    )
    reply = advisor.reply(uuid4(), "¿Cuál me sirve?")
    assert reply.projects == ["cipres", "arrayanes-del-sur"]


def test_a_reply_without_tools_names_no_projects() -> None:
    model = ScriptedChatModel(script=[answer("Hola, ¿qué buscas?")])
    assert make_advisor(model).reply(uuid4(), "Hola").projects == []
