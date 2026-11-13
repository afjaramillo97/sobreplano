"""Advisor value types: one LLM call's usage and the advisor's reply to a message."""

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sobreplano.domain.errors import DomainValidationError


@dataclass(frozen=True)
class LlmCall:
    """Model and tokens of one LLM call (constitution, principle 5).

    Raises:
        DomainValidationError: if a token count is negative.
    """

    model: str  # "provider:model" as configured, not the name the API echoes back
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal | None  # None when the model is not in the price table

    def __post_init__(self) -> None:
        if self.input_tokens < 0 or self.output_tokens < 0:
            raise DomainValidationError("token counts must be >= 0")


@dataclass(frozen=True)
class ToolCallRecord:
    """One tool call of a turn: what the model asked for and what the tool returned."""

    name: str
    args: dict[str, object]
    output: str  # the ToolMessage content (compact JSON, or the error text)


@dataclass(frozen=True)
class AdvisorReply:
    """The advisor's answer to one message, with the tools and LLM calls it took."""

    text: str
    tools_used: list[str]  # in call order, repeats included
    llm_calls: list[LlmCall]
    tool_calls: list[ToolCallRecord]  # in call order, with their arguments and results


@dataclass(frozen=True)
class AdvisorAnswer:
    """A reply together with the conversation it belongs to."""

    thread_id: UUID
    reply: AdvisorReply
