"""Unit tests for the advisor graph and adapter with a scripted model and in-memory memory."""

from collections.abc import Callable, Sequence
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import httpx2
import pytest
from langchain_core.callbacks import BaseCallbackHandler
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
from sobreplano.infrastructure.advisor.langgraph_advisor import UNVERIFIED_ANSWER, LangGraphAdvisor
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


class MetadataRecorder(BaseCallbackHandler):
    """Records the metadata of every chain run, as the Langfuse handler would read it."""

    def __init__(self) -> None:
        super().__init__()
        self.metadata: list[dict[str, Any]] = []

    def on_chain_start(self, serialized: dict[str, Any] | None, inputs: Any, **kwargs: Any) -> None:
        self.metadata.append(dict(kwargs.get("metadata") or {}))


def test_extra_callbacks_get_the_session_tags_and_prompt_version() -> None:
    recorder = MetadataRecorder()
    model = ScriptedChatModel(script=[answer("Hola.")])
    thread_id = uuid4()
    advisor = LangGraphAdvisor(
        chat_model=lambda: model,
        model_name=MODEL,
        tools=build_tools(EmptyQuery()),
        checkpointer=InMemorySaver(),
        callbacks=[recorder],
        tags=["cli"],
    )

    advisor.reply(thread_id, "Hola")

    root = recorder.metadata[0]
    assert root["langfuse_session_id"] == str(thread_id)
    assert root["langfuse_tags"] == ["cli"]
    assert root["prompt_version"] == SYSTEM_PROMPT.version
    assert root["model"] == MODEL


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


def _thread_texts(saver: InMemorySaver, thread_id: UUID) -> list[str]:
    checkpoint = saver.get_tuple({"configurable": {"thread_id": str(thread_id)}})
    assert checkpoint is not None
    return [m.text for m in checkpoint.checkpoint["channel_values"]["messages"]]


def test_personal_data_never_reaches_the_model_or_the_checkpoint() -> None:
    saver = InMemorySaver()
    model = ScriptedChatModel(script=[answer("Te mando opciones en Envigado.")])
    thread_id = uuid4()
    reply = make_advisor(model, saver).reply(
        thread_id,
        "Soy juan@example.com, mi celular es 300 123 4567 y mi cédula 43.123.456. "
        "¿Qué hay en Envigado?",
    )

    sent = " ".join(m.text for call in model.seen for m in call)
    stored = " ".join(_thread_texts(saver, thread_id))
    for original in ("juan@example.com", "300 123 4567", "43.123.456"):
        assert original not in sent
        assert original not in stored
    assert "[correo]" in sent and "[teléfono]" in sent and "[documento]" in sent
    assert "[correo]" in stored
    assert reply.guardrails == [
        "input_redacted:email",
        "input_redacted:phone",
        "input_redacted:id_number",
    ]


def test_a_message_without_personal_data_fires_no_guardrail() -> None:
    reply = make_advisor(ScriptedChatModel(script=[answer("Ok.")])).reply(
        uuid4(), "Busco algo de $450.000.000 en Sabaneta"
    )
    assert reply.guardrails == []


def test_personal_data_in_the_answer_is_redacted_in_the_reply_and_the_thread() -> None:
    saver = InMemorySaver()
    model = ScriptedChatModel(script=[answer("Escribe a ventas@constructora.co o al 3109876543.")])
    thread_id = uuid4()
    reply = make_advisor(model, saver).reply(thread_id, "¿Cómo contacto a la constructora?")

    assert reply.text == "Escribe a [correo] o al [teléfono]."
    assert reply.guardrails == ["output_redacted:email", "output_redacted:phone"]
    stored = _thread_texts(saver, thread_id)
    assert stored[-1] == reply.text
    assert len(stored) == 2  # the question and one final answer, replaced and not duplicated


def _final_answers(saver: InMemorySaver, thread_id: UUID) -> list[str]:
    """The answers without tool calls after the last user message: exactly one per turn."""
    checkpoint = saver.get_tuple({"configurable": {"thread_id": str(thread_id)}})
    assert checkpoint is not None
    messages = checkpoint.checkpoint["channel_values"]["messages"]
    last_human = max(i for i, m in enumerate(messages) if isinstance(m, HumanMessage))
    return [m.text for m in messages[last_human:] if isinstance(m, AIMessage) and not m.tool_calls]


def test_an_answer_whose_figures_have_a_source_is_not_retried() -> None:
    model = ScriptedChatModel(
        script=[
            tool_call(
                "simulate_mortgage",
                price_cop=400_000_000,
                annual_rate_ea_pct=12,
                years=20,
                down_payment_pct=30,
            ),
            # 400 millones and 12 % come from the arguments; 30 % is also the tool's default.
            answer("Para 400 millones al 12 % con 30 % de cuota inicial, mira la simulación."),
        ]
    )
    reply = make_advisor(model).reply(uuid4(), "¿Cuánto pagaría al mes?")
    assert reply.guardrails == []
    assert len(model.seen) == 2


def test_an_ungrounded_answer_is_rewritten_once() -> None:
    saver = InMemorySaver()
    model = ScriptedChatModel(
        script=[
            tool_call("search_projects", municipality="sabaneta"),
            answer("Hay uno desde 999 millones."),
            answer("No encontré proyectos en Sabaneta."),
        ]
    )
    thread_id = uuid4()
    reply = make_advisor(model, saver).reply(thread_id, "¿Qué hay en Sabaneta?")

    assert reply.text == "No encontré proyectos en Sabaneta."
    assert reply.guardrails == ["ungrounded_retry"]
    assert len(reply.llm_calls) == 3  # the rewrite is recorded like any call
    rewrite_prompt = model.seen[-1]
    assert isinstance(rewrite_prompt[-1], SystemMessage)
    assert "999 millones" in rewrite_prompt[-1].text
    assert _final_answers(saver, thread_id) == [reply.text]


def test_a_rewrite_that_is_still_ungrounded_leaves_the_fixed_answer() -> None:
    saver = InMemorySaver()
    model = ScriptedChatModel(
        script=[answer("Cuesta 999 millones."), answer("Mejor dicho, 888 millones.")]
    )
    thread_id = uuid4()
    reply = make_advisor(model, saver).reply(thread_id, "¿Cuánto cuesta Torres Demo?")

    assert reply.text == UNVERIFIED_ANSWER["es"]
    assert reply.guardrails == ["ungrounded_retry", "ungrounded_fallback"]
    assert _final_answers(saver, thread_id) == [UNVERIFIED_ANSWER["es"]]


def test_the_fixed_answer_follows_the_user_language() -> None:
    model = ScriptedChatModel(script=[answer("It costs 999 million."), answer("Say 888 million.")])
    reply = make_advisor(model).reply(uuid4(), "What is the price of Torres Demo?")
    assert reply.text == UNVERIFIED_ANSWER["en"]


def test_a_provider_error_in_the_rewrite_leaves_the_fixed_answer() -> None:
    def boom() -> AIMessage:
        raise APIConnectionError(request=httpx2.Request("POST", "https://api.openai.com"))

    model = ScriptedChatModel(script=[answer("Cuesta 999 millones."), boom])
    reply = make_advisor(model).reply(uuid4(), "¿Cuánto cuesta Torres Demo?")
    assert reply.text == UNVERIFIED_ANSWER["es"]
    assert reply.guardrails == ["ungrounded_retry", "ungrounded_fallback"]


def test_an_earlier_invented_figure_does_not_ground_a_later_one() -> None:
    saver = InMemorySaver()
    thread_id = uuid4()
    model = ScriptedChatModel(script=[answer("Cuesta 999 millones."), answer("No lo sé.")])
    make_advisor(model, saver).reply(thread_id, "¿Cuánto cuesta?")

    model.script = [answer("Como te dije, 999 millones."), answer("No tengo ese dato.")]
    reply = make_advisor(model, saver).reply(thread_id, "¿Seguro?")
    assert reply.text == "No tengo ese dato."
    assert reply.guardrails == ["ungrounded_retry"]
