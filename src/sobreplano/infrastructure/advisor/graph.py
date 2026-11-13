"""The advisor's LangGraph loop, built by hand: model node, ToolNode and tools_condition."""

from collections.abc import Sequence
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AnyMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver

# langgraph.graph ships no stubs, and its builder overloads mention a generic CachePolicy that
# pyright strict reports as partly unknown; the ignores below are only for that.
from langgraph.graph import START, MessagesState, StateGraph  # pyright: ignore[reportMissingTypeStubs]
from langgraph.graph.state import CompiledStateGraph  # pyright: ignore[reportMissingTypeStubs]
from langgraph.prebuilt import ToolNode, tools_condition

from sobreplano.infrastructure.advisor.prompts import SYSTEM_PROMPT
from sobreplano.infrastructure.advisor.tools import handle_tool_error

MAX_TOOL_ROUNDS = 5
# One step per agent call and one per tool round: 5 rounds plus the final answer.
RECURSION_LIMIT = 2 * MAX_TOOL_ROUNDS + 1
MAX_QUESTIONS_IN_CONTEXT = 8


def recent_messages(messages: Sequence[AnyMessage], questions: int) -> list[AnyMessage]:
    """The messages from the `questions`-th last user message on.

    Cutting at a user message never leaves a tool call without its tool result, which the
    API would reject.
    """
    user_indexes = [i for i, message in enumerate(messages) if isinstance(message, HumanMessage)]
    if len(user_indexes) <= questions:
        return list(messages)
    return list(messages[user_indexes[-questions] :])


def build_advisor_graph(
    chat_model: BaseChatModel,
    tools: Sequence[BaseTool],
    checkpointer: BaseCheckpointSaver[Any],
) -> CompiledStateGraph[MessagesState, None, MessagesState, MessagesState]:
    """START → agent → (tools → agent)* → END, with memory per thread_id in checkpointer.

    Compiled per request, because the tools carry that request's database session.
    """
    model = chat_model.bind_tools(tools)

    def agent(state: MessagesState) -> dict[str, list[BaseMessage]]:
        context = recent_messages(state["messages"], MAX_QUESTIONS_IN_CONTEXT)
        return {"messages": [model.invoke([SystemMessage(SYSTEM_PROMPT), *context])]}

    builder = StateGraph(MessagesState)
    builder.add_node("agent", agent)  # pyright: ignore[reportUnknownMemberType]
    builder.add_node(  # pyright: ignore[reportUnknownMemberType]
        "tools", ToolNode(tools, handle_tool_errors=handle_tool_error)
    )
    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", tools_condition)
    builder.add_edge("tools", "agent")
    return builder.compile(checkpointer=checkpointer)  # pyright: ignore[reportUnknownMemberType]
