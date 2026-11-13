"""Unit tests for the advisor graph and adapter with a scripted model and in-memory memory."""

from collections.abc import Callable, Sequence
from decimal import Decimal
from typing import Any
from uuid import uuid4

import httpx2
import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult, LLMResult
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from openai import APIConnectionError
from pydantic import Field, SecretStr

from sobreplano.domain.errors import AdvisorLimitError, AdvisorUnavailableError
from sobreplano.domain.listings import (
    DeveloperSummary,
    ProjectDetail,
    ProjectFilters,
    ProjectPage,
    ProjectSort,
)
from sobreplano.infrastructure.advisor.chat_models import build_chat_model
from sobreplano.infrastructure.advisor.graph import MAX_TOOL_ROUNDS, SYSTEM_PROMPT, recent_messages
from sobreplano.infrastructure.advisor.langgraph_advisor import LangGraphAdvisor
from sobreplano.infrastructure.advisor.tools import build_tools
from sobreplano.infrastructure.advisor.usage_callback import UsageCallback
from sobreplano.infrastructure.settings import Settings

MODEL = "openai:gpt-6-luna"
USAGE = {"input_tokens": 1000, "output_tokens": 100, "total_tokens": 1100}


class ScriptedChatModel(BaseChatModel):
    """Answers with the next scripted message and records what it was sent.

    Each script entry is a factory: add_messages assigns ids in place, so a message object
    must never be returned twice.
    """

    script: list[Callable[[], AIMessage]]
    seen: list[list[BaseMessage]] = Field(default_factory=list[list[BaseMessage]])
    error: Exception | None = None

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
        self.seen.append(list(messages))
        if self.error is not None:
            raise self.error
        factory = self.script[0] if len(self.script) == 1 else self.script.pop(0)
        return ChatResult(generations=[ChatGeneration(message=factory())])

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


def make_advisor(model: ScriptedChatModel, saver: InMemorySaver | None = None) -> LangGraphAdvisor:
    return LangGraphAdvisor(
        chat_model=lambda: model,
        model_name=MODEL,
        tools=build_tools(EmptyQuery()),
        checkpointer=saver or InMemorySaver(),
    )


def test_question_that_searches_and_answers() -> None:
    model = ScriptedChatModel(
        script=[tool_call("search_projects", municipality="sabaneta"), answer("No encontré.")]
    )
    reply = make_advisor(model).reply(uuid4(), "¿Qué hay en Sabaneta?")

    assert reply.text == "No encontré."
    assert reply.tools_used == ["search_projects"]
    # The second call saw the tool result.
    assert isinstance(model.seen[1][-1], ToolMessage)
    assert '"total":0' in str(model.seen[1][-1].content)


def test_every_llm_call_has_model_tokens_and_cost() -> None:
    model = ScriptedChatModel(script=[tool_call("list_developers"), answer("Listo.")])
    reply = make_advisor(model).reply(uuid4(), "¿Qué constructoras hay?")

    assert len(reply.llm_calls) == 2
    for call in reply.llm_calls:
        assert (call.model, call.input_tokens, call.output_tokens) == (MODEL, 1000, 100)
        assert call.prompt_version == SYSTEM_PROMPT.version
        # 1000 * 0.10 + 100 * 0.50 per million tokens.
        assert call.cost_usd == Decimal("0.000150")


def test_system_prompt_goes_first() -> None:
    model = ScriptedChatModel(script=[answer("Hola.")])
    make_advisor(model).reply(uuid4(), "Hola")
    first = model.seen[0][0]
    assert isinstance(first, SystemMessage)
    assert first.content == SYSTEM_PROMPT.text


def test_second_question_in_the_same_thread_sees_the_first() -> None:
    saver = InMemorySaver()
    model = ScriptedChatModel(script=[answer("Primera respuesta.")])
    thread_id = uuid4()
    make_advisor(model, saver).reply(thread_id, "Primera pregunta")

    model.script = [answer("Segunda respuesta.")]
    reply = make_advisor(model, saver).reply(thread_id, "¿Y la segunda?")

    texts = [message.text for message in model.seen[-1]]
    assert "Primera pregunta" in texts and "Primera respuesta." in texts
    assert texts[-1] == "¿Y la segunda?"
    # tools_used and llm_calls only cover the new turn.
    assert reply.tools_used == []
    assert len(reply.llm_calls) == 1


def test_another_thread_does_not_see_the_first() -> None:
    saver = InMemorySaver()
    model = ScriptedChatModel(script=[answer("Ok.")])
    make_advisor(model, saver).reply(uuid4(), "Secreto")
    make_advisor(model, saver).reply(uuid4(), "Otra conversación")
    assert "Secreto" not in [message.text for message in model.seen[-1]]


def test_a_model_that_always_calls_tools_hits_the_limit_with_its_calls() -> None:
    model = ScriptedChatModel(script=[tool_call("list_developers")])
    with pytest.raises(AdvisorLimitError) as raised:
        make_advisor(model).reply(uuid4(), "Bucle")
    # One model call per tool round plus the one that would have answered.
    assert len(raised.value.llm_calls) == MAX_TOOL_ROUNDS + 1
    assert all(call.model == MODEL for call in raised.value.llm_calls)


def unanswered_tool_calls(messages: list[BaseMessage]) -> list[str]:
    answered = {message.tool_call_id for message in messages if isinstance(message, ToolMessage)}
    return [
        call["id"] or ""
        for message in messages
        if isinstance(message, AIMessage)
        for call in message.tool_calls
        if call["id"] not in answered
    ]


def test_orphan_tool_call_is_closed_so_the_thread_keeps_answering() -> None:
    saver = InMemorySaver()
    thread_id = uuid4()
    model = ScriptedChatModel(script=[tool_call("list_developers")])
    with pytest.raises(AdvisorLimitError):
        make_advisor(model, saver).reply(thread_id, "Bucle")

    model.script = [answer("Ya respondo.")]
    reply = make_advisor(model, saver).reply(thread_id, "¿Sigues ahí?")

    assert reply.text == "Ya respondo."
    sent = model.seen[-1]
    assert unanswered_tool_calls(sent) == []
    closing = [m for m in sent if isinstance(m, ToolMessage) and "round limit" in m.text]
    assert len(closing) == 1
    assert closing[0].text == '{"error": "tool round limit reached"}'


def test_provider_error_makes_the_advisor_unavailable() -> None:
    error = APIConnectionError(request=httpx2.Request("POST", "https://api.openai.com"))
    model = ScriptedChatModel(script=[answer("x")], error=error)
    with pytest.raises(AdvisorUnavailableError):
        make_advisor(model).reply(uuid4(), "Hola")


def test_repeated_tools_are_kept_in_order() -> None:
    model = ScriptedChatModel(
        script=[
            tool_call("search_projects"),
            tool_call("get_project", slug="a"),
            tool_call("search_projects"),
            answer("Fin."),
        ]
    )
    reply = make_advisor(model).reply(uuid4(), "Busca")
    assert reply.tools_used == ["search_projects", "get_project", "search_projects"]


def test_tool_calls_keep_arguments_and_results_in_order() -> None:
    model = ScriptedChatModel(
        script=[
            tool_call("search_projects", municipality="sabaneta"),
            tool_call("list_developers"),
            answer("Fin."),
        ]
    )
    reply = make_advisor(model).reply(uuid4(), "Busca")

    assert [call.name for call in reply.tool_calls] == ["search_projects", "list_developers"]
    assert reply.tool_calls[0].args == {"municipality": "sabaneta"}
    assert '"total":0' in reply.tool_calls[0].output
    assert reply.tool_calls[1].args == {}
    assert reply.tool_calls[1].output == '{"developers":[]}'


def test_tool_call_with_bad_arguments_records_the_error() -> None:
    model = ScriptedChatModel(
        script=[tool_call("search_projects", min_price=-1), answer("Corrijo.")]
    )
    reply = make_advisor(model).reply(uuid4(), "Busca")

    [call] = reply.tool_calls
    assert call.args == {"min_price": -1}
    assert "min_price: Input should be greater than 0" in call.output


def test_recent_messages_cuts_at_a_user_message() -> None:
    messages: list[Any] = []
    for i in range(10):
        messages += [
            HumanMessage(f"q{i}"),
            AIMessage(content="", tool_calls=[{"id": f"c{i}", "name": "x", "args": {}}]),
            ToolMessage(content="{}", tool_call_id=f"c{i}"),
            AIMessage(content=f"a{i}"),
        ]
    kept = recent_messages(messages, 8)
    assert isinstance(kept[0], HumanMessage) and kept[0].content == "q2"
    assert len(kept) == 8 * 4


def test_recent_messages_keeps_everything_when_short() -> None:
    messages: list[Any] = [HumanMessage("q"), AIMessage(content="a")]
    assert recent_messages(messages, 8) == messages


def test_usage_callback_without_metadata_counts_zero_and_unknown_model_costs_none() -> None:
    callback = UsageCallback("openai:unpriced", None)
    callback.on_llm_end(
        LLMResult(generations=[[ChatGeneration(message=AIMessage(content="x"))]]),
        run_id=uuid4(),
    )
    [call] = callback.calls
    assert (call.input_tokens, call.output_tokens, call.cost_usd) == (0, 0, None)


def settings(**overrides: Any) -> Settings:
    return Settings(database_url="postgresql+psycopg://x", **overrides)


def test_chat_model_without_key_is_unavailable() -> None:
    with pytest.raises(AdvisorUnavailableError, match="OPENAI_API_KEY"):
        build_chat_model(settings(openai_api_key=None))


@pytest.mark.parametrize("model", ["gpt-6-luna", "acme:gpt", ":gpt", "openai:"])
def test_chat_model_rejects_a_bad_advisor_model(model: str) -> None:
    with pytest.raises(ValueError, match="ADVISOR_MODEL"):
        build_chat_model(settings(advisor_model=model, openai_api_key=SecretStr("sk-test")))


def test_chat_model_caps_tokens_and_sends_no_temperature() -> None:
    chat = build_chat_model(
        settings(openai_api_key=SecretStr("sk-test"), advisor_reasoning_effort="medium")
    )
    assert isinstance(chat, ChatOpenAI)
    assert chat.model_name == "gpt-6-luna"
    assert chat.max_tokens == 1024
    assert chat.reasoning_effort == "medium"
    assert chat.temperature is None
