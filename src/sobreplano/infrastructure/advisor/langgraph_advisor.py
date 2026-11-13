"""LangGraph implementation of the AdvisorAgent port."""

from collections.abc import Callable, Sequence
from typing import Any
from uuid import UUID

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.errors import GraphRecursionError
from openai import APIError

from sobreplano.domain.advisor import AdvisorReply
from sobreplano.domain.errors import AdvisorLimitError, AdvisorUnavailableError
from sobreplano.infrastructure.advisor.graph import RECURSION_LIMIT, build_advisor_graph
from sobreplano.infrastructure.advisor.usage_callback import UsageCallback


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
        answer = new_messages[-1]
        return AdvisorReply(
            text=answer.text if isinstance(answer, AIMessage) else "",
            tools_used=tools_used,
            llm_calls=usage.calls,
        )
