"""LangGraph implementation of the AdvisorAgent port."""

from collections.abc import Callable, Sequence
from typing import Any
from uuid import UUID

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
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
from sobreplano.infrastructure.advisor.graph import RECURSION_LIMIT, build_advisor_graph
from sobreplano.infrastructure.advisor.usage_callback import UsageCallback

ORPHAN_TOOL_RESULT = '{"error": "tool round limit reached"}'


class LangGraphAdvisor:
    """Answers a message by running the advisor graph on the conversation's checkpoint."""

    def __init__(
        self,
        chat_model: Callable[[], BaseChatModel],
        model_name: str,
        tools: Sequence[BaseTool],
        checkpointer: BaseCheckpointSaver[Any],
    ) -> None:
        # A factory, so a missing API key fails on the first message and not before the
        # use case has checked the budget.
        self._chat_model = chat_model
        self._model_name = model_name
        self._tools = tools
        self._checkpointer = checkpointer

    def reply(self, thread_id: UUID, message: str) -> AdvisorReply:
        """Run one turn of the conversation and return the last answer.

        Raises:
            AdvisorUnavailableError: if there is no API key or the provider fails.
            AdvisorLimitError: if the turn needs more than MAX_TOOL_ROUNDS tool rounds;
                it carries the LLM calls made so they can be recorded.
        """
        graph = build_advisor_graph(self._chat_model(), self._tools, self._checkpointer)
        usage = UsageCallback(self._model_name)
        config: RunnableConfig = {
            "configurable": {"thread_id": str(thread_id)},
            "recursion_limit": RECURSION_LIMIT,
            "callbacks": [usage],
        }
        before = len(graph.get_state(config).values.get("messages", []))
        try:
            # Partly unknown overloads in langgraph's invoke (see graph.py).
            result = graph.invoke(  # pyright: ignore[reportUnknownMemberType]
                {"messages": [HumanMessage(message)]}, config
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
        return AdvisorReply(
            text=answer.text if isinstance(answer, AIMessage) else "",
            tools_used=tools_used,
            llm_calls=usage.calls,
            tool_calls=tool_calls,
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
