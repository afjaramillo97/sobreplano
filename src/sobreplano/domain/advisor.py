"""Advisor value types: one LLM call's usage and the advisor's reply to a message."""

from dataclasses import dataclass
from decimal import Decimal

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
