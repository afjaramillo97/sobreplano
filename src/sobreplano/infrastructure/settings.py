"""Application settings read from the environment."""

from decimal import Decimal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Environment-backed configuration; DATABASE_URL is required and non-empty."""

    database_url: str = Field(min_length=1)
    # "provider:model"; see infrastructure/llm/providers.py for the known providers.
    extraction_model: str = "openai:gpt-6-luna"
    # Optional: without it nothing new is extracted, but stored extractions are still reused.
    openai_api_key: SecretStr | None = None
    # Optional: OpenRouter models ("openrouter:qwen/qwen3.7-flash"), same rule as OpenAI's key.
    openrouter_api_key: SecretStr | None = None
    # "data/raw" (default, local disk) or "s3://bucket-name".
    raw_store: str = "data/raw"
    # Advisor (SPEC 08): same "provider:model" table as the extractor. The final model is
    # chosen by the golden set of SPEC 09.
    advisor_model: str = "openai:gpt-6-luna"
    # SPEC 09: Luna passes the golden set at medium, not at low.
    advisor_reasoning_effort: str = "medium"
    # 0.20 USD a day caps the worst month at 6 USD, inside the project's 20 USD budget.
    advisor_daily_budget_usd: Decimal = Decimal("0.20")
    advisor_max_turns: int = Field(default=20, gt=0)
    # Langfuse Cloud (SPEC 09): optional; without both keys there are no traces.
    langfuse_public_key: str | None = None
    langfuse_secret_key: SecretStr | None = None
    langfuse_base_url: str = "https://us.cloud.langfuse.com"


def load_settings() -> Settings:
    """Read the settings from the environment.

    Raises:
        pydantic.ValidationError: if a required variable is missing or empty.
    """
    # Pyright strict does not know BaseSettings fills database_url from the environment.
    return Settings()  # pyright: ignore[reportCallIssue]
