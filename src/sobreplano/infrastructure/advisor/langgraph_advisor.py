"""LangGraph implementation of the AdvisorAgent port."""

from collections.abc import Callable, Sequence
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.errors import GraphRecursionError

# No stubs in langgraph.graph; see graph.py.
from langgraph.graph import MessagesState  # pyright: ignore[reportMissingTypeStubs]
from langgraph.graph.state import CompiledStateGraph  # pyright: ignore[reportMissingTypeStubs]
from openai import APIError

from sobreplano.domain.advisor import AdvisorReply, ToolCallRecord
from sobreplano.domain.errors import AdvisorLimitError, AdvisorUnavailableError
from sobreplano.domain.figures import ungrounded_figures
from sobreplano.domain.language import Language, detect_language
from sobreplano.domain.privacy import redact_personal_data
from sobreplano.infrastructure.advisor.graph import (
    MAX_QUESTIONS_IN_CONTEXT,
    RECURSION_LIMIT,
    SYSTEM_PROMPT,
    build_advisor_graph,
    recent_messages,
)
from sobreplano.infrastructure.advisor.grounding import (
    thread_source_numbers,
    tool_definition_numbers,
)
from sobreplano.infrastructure.advisor.tools import DETAIL_LIMIT_RESULT
from sobreplano.infrastructure.advisor.usage_callback import UsageCallback

ORPHAN_TOOL_RESULT = '{"error": "tool round limit reached"}'
REWRITE_NOTE = (
    "These figures are not in any tool result: {figures}. Rewrite the answer using only "
    "figures from tool results, or say you do not have them."
)
# The answer when the rewrite still has figures with no source, in the user's language.
UNVERIFIED_ANSWER: dict[Language, str] = {
    "es": (
        "No pude verificar algunas cifras de mi respuesta; ¿puedes reformular la pregunta "
        "o pedirme un proyecto en particular?"
    ),
    "en": (
        "I could not verify some figures in my answer; could you rephrase the question "
        "or ask me about a specific project?"
    ),
}


class LangGraphAdvisor:
    """Answers a message by running the advisor graph on the conversation's checkpoint."""

    def __init__(
        self,
        chat_model: Callable[[], BaseChatModel],
        model_name: str,
        tools: Callable[[], Sequence[BaseTool]],
        checkpointer: BaseCheckpointSaver[Any],
        callbacks: Sequence[BaseCallbackHandler] = (),
        tags: Sequence[str] = (),
    ) -> None:
        # A factory, so a missing API key fails on the first message and not before the
        # use case has checked the budget.
        self._chat_model = chat_model
        self._model_name = model_name
        self._tools = tools
        # A factory: each message gets fresh tools, so their per-message detail limit starts
        # at zero whoever calls the advisor (API, terminal or evals).
        # Defaults and limits the model is told about, such as the 30 % down payment.
        self._known_numbers = tool_definition_numbers(tools())
        self._checkpointer = checkpointer
        # Tracing (Langfuse): extra callbacks, and tags that say where the turn came from.
        self._callbacks = list(callbacks)
        self._tags = list(tags)

    def reply(self, thread_id: UUID, message: str) -> AdvisorReply:
        """Run one turn of the conversation and return the last answer.

        Personal data in message is redacted before the graph runs, so the model, the memory
        and Langfuse only ever see the redacted text; the answer is redacted too, in the
        reply and in the thread.

        Every figure of the answer must come from the thread (user messages, tool results
        and arguments) or the tool definitions. If one does not, the model rewrites the
        answer once without tools; if the rewrite still has one, the answer is a fixed text.
        Either way the thread keeps a single final answer.

        Raises:
            AdvisorUnavailableError: if there is no API key or the provider fails.
            AdvisorLimitError: if the turn needs more than MAX_TOOL_ROUNDS tool rounds;
                it carries the LLM calls made so they can be recorded.
        """
        redacted = redact_personal_data(message)
        guardrails = _events("input_redacted", redacted.kinds)
        chat_model = self._chat_model()
        tools = self._tools()
        graph = build_advisor_graph(chat_model, tools, self._checkpointer)
        usage = UsageCallback(self._model_name, SYSTEM_PROMPT.version)
        config: RunnableConfig = {
            "configurable": {"thread_id": str(thread_id)},
            "recursion_limit": RECURSION_LIMIT,
            "callbacks": [usage, *self._callbacks],
            # Read by the Langfuse handler: the conversation is the session.
            "metadata": {
                "langfuse_session_id": str(thread_id),
                "langfuse_tags": [*self._tags, *guardrails],
                "prompt_version": SYSTEM_PROMPT.version,
                "model": self._model_name,
            },
        }
        before = len(graph.get_state(config).values.get("messages", []))
        try:
            # Partly unknown overloads in langgraph's invoke (see graph.py).
            result = graph.invoke(  # pyright: ignore[reportUnknownMemberType]
                {"messages": [HumanMessage(redacted.text)]}, config
            )
        except GraphRecursionError as error:
            _close_orphan_tool_calls(graph, config)
            raise AdvisorLimitError("too many tool rounds", usage.calls) from error
        except APIError as error:
            raise AdvisorUnavailableError(f"provider error: {type(error).__name__}") from error

        new_messages = result["messages"][before:]
        tools_used = [
            call["name"]
            for message in new_messages
            if isinstance(message, AIMessage)
            for call in message.tool_calls
        ]
        outputs = {
            message.tool_call_id: message.text
            for message in new_messages
            if isinstance(message, ToolMessage)
        }
        tool_calls = [
            ToolCallRecord(
                name=call["name"],
                args=dict(call["args"]),
                output=outputs.get(call["id"] or "", ""),
            )
            for message in new_messages
            if isinstance(message, AIMessage)
            for call in message.tool_calls
        ]
        answer = new_messages[-1]
        # Redact before checking figures, so a phone number is never read as an amount.
        output = redact_personal_data(answer.text if isinstance(answer, AIMessage) else "")
        text, kinds = output.text, output.kinds
        if isinstance(answer, AIMessage):
            text, events = self._grounded_text(chat_model, tools, config, result["messages"], text)
            rewrite = redact_personal_data(text)  # the rewrite may rebuild personal data
            text, kinds = rewrite.text, [*kinds, *rewrite.kinds]
            guardrails += events
            if text != answer.text:
                # A rewritten or redacted answer replaces the original in the thread too.
                _replace_message(graph, config, answer, text)
        guardrails += _events("output_redacted", kinds)
        if any(call.output == DETAIL_LIMIT_RESULT for call in tool_calls):
            guardrails.append("detail_limit")
        return AdvisorReply(
            text=text,
            tools_used=tools_used,
            llm_calls=usage.calls,
            tool_calls=tool_calls,
            guardrails=guardrails,
        )

    def _grounded_text(
        self,
        chat_model: BaseChatModel,
        tools: Sequence[BaseTool],
        config: RunnableConfig,
        messages: Sequence[AnyMessage],
        text: str,
    ) -> tuple[str, list[str]]:
        """The answer if all its figures have a source, else one rewrite, else a fixed text.

        Returns the text to keep and the guardrail events that fired.
        """
        sources = [*thread_source_numbers(messages), *self._known_numbers]
        ungrounded = ungrounded_figures(text, sources)
        if not ungrounded:
            return text, []
        note = REWRITE_NOTE.format(figures=", ".join(f.raw for f in ungrounded))
        context = recent_messages(messages, MAX_QUESTIONS_IN_CONTEXT)
        # Tools stay declared, because some providers reject a history with tool calls and
        # no tools, but tool_choice="none" forbids calling them: the rewrite can only use
        # what the thread already has. The config's UsageCallback records the call.
        model = chat_model.bind_tools(tools, tool_choice="none")
        try:
            rewrite = model.invoke(
                [SystemMessage(SYSTEM_PROMPT.text), *context, SystemMessage(note)], config
            )
        except APIError:
            # The answer was already there; a failed rewrite is not a failed turn.
            return _unverified(messages), ["ungrounded_retry", "ungrounded_fallback"]
        rewritten = rewrite.text
        if rewritten.strip() and not ungrounded_figures(rewritten, sources):
            return rewritten, ["ungrounded_retry"]
        return _unverified(messages), ["ungrounded_retry", "ungrounded_fallback"]


def _unverified(messages: Sequence[AnyMessage]) -> str:
    """The fixed answer, in the language of the last user message."""
    last = next((m.text for m in reversed(messages) if isinstance(m, HumanMessage)), "")
    return UNVERIFIED_ANSWER[detect_language(last)]


def _events(prefix: str, kinds: Sequence[str]) -> list[str]:
    """One "prefix:kind" event per distinct kind, in order of appearance."""
    return [f"{prefix}:{kind}" for kind in dict.fromkeys(kinds)]


def _replace_message(
    graph: CompiledStateGraph[MessagesState, None, MessagesState, MessagesState],
    config: RunnableConfig,
    message: AIMessage,
    text: str,
) -> None:
    """Replace the content of a final answer in the thread, keeping its id.

    add_messages replaces by id. as_node="agent" with no tool calls routes to END, so no
    step is left pending.
    """
    graph.update_state(
        config, {"messages": [AIMessage(content=text, id=message.id)]}, as_node="agent"
    )


def _close_orphan_tool_calls(
    graph: CompiledStateGraph[MessagesState, None, MessagesState, MessagesState],
    config: RunnableConfig,
) -> None:
    """Answer the tool calls left pending when the round limit stopped the graph.

    The API rejects a history with a tool call and no tool result, so without this the
    thread would fail on every later message.
    """
    messages = graph.get_state(config).values.get("messages", [])
    last = messages[-1] if messages else None
    if not isinstance(last, AIMessage) or not last.tool_calls:
        return
    closing = [
        ToolMessage(content=ORPHAN_TOOL_RESULT, tool_call_id=call["id"] or "")
        for call in last.tool_calls
    ]
    # as_node="tools": the checkpoint then looks like a finished tool round.
    graph.update_state(config, {"messages": closing}, as_node="tools")
