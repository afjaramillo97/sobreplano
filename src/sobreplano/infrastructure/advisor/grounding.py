"""The numbers an advisor answer may quote: from the thread's messages and the tool definitions."""

import json
import re
from collections.abc import Sequence
from decimal import Decimal

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage
from langchain_core.tools import BaseTool
from pydantic import BaseModel

from sobreplano.domain.figures import all_numbers

# "e.g. 12 for 12 %" is an example, not a fact: an invented 12 % rate must not pass.
_EXAMPLE = re.compile(r"e\.g\.[^.]*")


def tool_definition_numbers(tools: Sequence[BaseTool]) -> list[Decimal]:
    """Numbers in what the model is told about each tool: description, defaults and limits.

    Examples ("e.g. ...") are left out.
    """
    numbers: list[Decimal] = []
    for tool in tools:
        texts = [tool.description]
        if isinstance(tool.args_schema, type) and issubclass(tool.args_schema, BaseModel):
            texts.append(json.dumps(tool.args_schema.model_json_schema()))
        numbers += [n for text in texts for n in all_numbers(_EXAMPLE.sub("", text))]
    return numbers


def thread_source_numbers(messages: Sequence[AnyMessage]) -> list[Decimal]:
    """Every number in the thread's user messages, tool results and tool call arguments.

    The advisor's own earlier answers are not sources: a figure it invented once must not
    ground the next one.
    """
    numbers: list[Decimal] = []
    for message in messages:
        if isinstance(message, HumanMessage | ToolMessage):
            numbers += all_numbers(message.text)
        elif isinstance(message, AIMessage):
            # Arguments such as down_payment_pct=20 are what a tool computed with; the
            # simulations do not echo them in their results.
            numbers += [
                Decimal(str(value))
                for call in message.tool_calls
                for value in call["args"].values()
                if isinstance(value, int | float) and not isinstance(value, bool)
            ]
    return numbers
