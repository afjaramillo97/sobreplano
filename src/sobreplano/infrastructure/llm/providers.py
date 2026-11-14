"""Provider table and factory for EXTRACTION_MODEL ("provider:model")."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from openai import OpenAI
from pydantic import SecretStr

from sobreplano.infrastructure.scraping.openai_compatible_extractor import (
    OpenAICompatibleExtractor,
    UnavailableExtractor,
)
from sobreplano.infrastructure.settings import Settings

REQUEST_TIMEOUT_SECONDS = 60.0


@dataclass(frozen=True)
class Provider:
    """How to reach one OpenAI-compatible API."""

    base_url: str | None  # None: the SDK's default, api.openai.com
    api_key_variable: str  # for the error message
    api_key: Callable[[Settings], SecretStr | None]
    extra: Mapping[str, object]  # provider-specific request parameters


PROVIDERS: dict[str, Provider] = {
    # Reasoning defaults to medium and its tokens bill as output; extraction needs none.
    "openai": Provider(
        base_url=None,
        api_key_variable="OPENAI_API_KEY",
        api_key=lambda settings: settings.openai_api_key,
        extra={"reasoning_effort": "none"},
    ),
    # One key for many models (SPEC 09). Checked on openrouter.ai on 2026-11-13: Qwen3.7 Flash
    # reasons by default but allows turning it off. No require_parameters: with a json_schema
    # response_format it asks for "structured_outputs", which the catalog does not list, and
    # answers 404; the schema is validated by pydantic after the call anyway.
    "openrouter": Provider(
        base_url="https://openrouter.ai/api/v1",
        api_key_variable="OPENROUTER_API_KEY",
        api_key=lambda settings: settings.openrouter_api_key,
        extra={"extra_body": {"reasoning": {"enabled": False}}},
    ),
}


# USD per million tokens (input, output), for the cost estimate in the run summary.
# Prices as stated in SPEC 04 (2026-10-30); update when a price or the default model changes.
MODEL_PRICES_USD_PER_MILLION: dict[str, tuple[float, float]] = {
    "openai:gpt-6-luna": (0.10, 0.50),
    # Judge of the advisor evals (SPEC 09); checked on developers.openai.com on 2026-11-13.
    "openai:gpt-6.1-terra": (1.00, 5.00),
    # Stronger judge candidate; developers.openai.com pricing page, 2026-11-13.
    "openai:gpt-6.1-sol": (2.00, 10.00),
    # Extraction candidate (SPEC 09); OpenRouter's listed price on 2026-11-13.
    "openrouter:qwen/qwen3.7-flash": (0.03, 0.13),
}


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float | None:
    """Cost of the given tokens with the model's list price, or None if the price is unknown."""
    prices = MODEL_PRICES_USD_PER_MILLION.get(model)
    if prices is None:
        return None
    input_price, output_price = prices
    return (input_tokens * input_price + output_tokens * output_price) / 1_000_000


def build_extractor(settings: Settings) -> OpenAICompatibleExtractor | UnavailableExtractor:
    """The extractor for settings.extraction_model.

    Without an API key it returns an UnavailableExtractor, so a run can still reuse stored
    extractions.

    Raises:
        ValueError: if extraction_model is not "provider:model" or the provider is unknown,
            so a typo fails at startup and not on the first page.
    """
    provider_name, separator, api_model = settings.extraction_model.partition(":")
    if not separator or not provider_name or not api_model:
        raise ValueError(
            f"EXTRACTION_MODEL must be provider:model, got {settings.extraction_model!r}"
        )
    provider = PROVIDERS.get(provider_name)
    if provider is None:
        raise ValueError(
            f"unknown provider {provider_name!r} in EXTRACTION_MODEL; known: {sorted(PROVIDERS)}"
        )

    api_key = provider.api_key(settings)
    if api_key is None or not api_key.get_secret_value():
        return UnavailableExtractor(
            settings.extraction_model, f"{provider.api_key_variable} is not set"
        )
    client = OpenAI(
        api_key=api_key.get_secret_value(),
        base_url=provider.base_url,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    return OpenAICompatibleExtractor(
        client, model=settings.extraction_model, api_model=api_model, extra=provider.extra
    )
