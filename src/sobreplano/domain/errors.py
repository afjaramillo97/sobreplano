"""Domain-level exceptions."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # advisor.py imports DomainValidationError from here; only the type is needed.
    from sobreplano.domain.advisor import LlmCall


class DomainValidationError(ValueError):
    """Raised when a domain entity is built with values that break its invariants."""


class FetchError(Exception):
    """Raised when a page cannot be fetched: network error, timeout, redirects or robots.txt."""


class PageParseError(Exception):
    """Raised when an in-scope page lacks a structured field the parser needs (canonical, map)."""


class ExtractionError(Exception):
    """Raised when the model gives no usable extraction: refusal, cut-off, empty or no API key."""


class DuplicateObservationError(Exception):
    """Raised by a repository when the unit type already has an observation that day."""


class AdvisorUnavailableError(Exception):
    """Raised when the advisor cannot reach its model: no API key or the provider fails."""


class AdvisorBudgetExceededError(Exception):
    """Raised when the advisor's daily budget in USD is spent; the model is not called."""


class AdvisorTurnLimitError(Exception):
    """Raised when a conversation already has the maximum number of messages."""


class AdvisorThreadNotFoundError(Exception):
    """Raised when a thread_id is unknown or the conversation was deleted."""


class AdvisorLimitError(Exception):
    """Raised when one message needs more tool rounds than allowed.

    Carries the LLM calls made before giving up, so their cost is still recorded.
    """

    def __init__(self, message: str, llm_calls: "list[LlmCall]") -> None:
        super().__init__(message)
        self.llm_calls = llm_calls
