"""Builds the advisor's chat model from ADVISOR_MODEL ("provider:model")."""

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from sobreplano.domain.errors import AdvisorUnavailableError
from sobreplano.infrastructure.llm.providers import PROVIDERS, REQUEST_TIMEOUT_SECONDS
from sobreplano.infrastructure.settings import Settings

MAX_COMPLETION_TOKENS = 1024  # per model call; caps the cost of one long answer


def build_chat_model(settings: Settings) -> BaseChatModel:
    """A ChatOpenAI client on the provider's base URL and key, without temperature.

    Called on the first message, not at API startup, so a missing key only disables the
    advisor.

    Raises:
        ValueError: if ADVISOR_MODEL is not "provider:model" or the provider is unknown.
        AdvisorUnavailableError: if the provider's API key is not set.
    """
    provider_name, separator, api_model = settings.advisor_model.partition(":")
    if not separator or not provider_name or not api_model:
        raise ValueError(f"ADVISOR_MODEL must be provider:model, got {settings.advisor_model!r}")
    provider = PROVIDERS.get(provider_name)
    if provider is None:
        raise ValueError(
            f"unknown provider {provider_name!r} in ADVISOR_MODEL; known: {sorted(PROVIDERS)}"
        )
    api_key = provider.api_key(settings)
    if api_key is None or not api_key.get_secret_value():
        raise AdvisorUnavailableError(f"{provider.api_key_variable} is not set")
    # Reasoning models reject temperature, so it is never sent. The provider's `extra` is
    # left out: it holds the extractor's settings (reasoning off), not the advisor's.
    return ChatOpenAI(
        model=api_model,
        api_key=api_key,
        base_url=provider.base_url,
        max_completion_tokens=MAX_COMPLETION_TOKENS,
        reasoning_effort=settings.advisor_reasoning_effort,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
