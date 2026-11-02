"""Application settings read from the environment."""

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Environment-backed configuration; DATABASE_URL is required and non-empty."""

    database_url: str = Field(min_length=1)
    # "provider:model"; see infrastructure/scraping/providers.py for the known providers.
    extraction_model: str = "openai:gpt-6-luna"
    # Optional: without it nothing new is extracted, but stored extractions are still reused.
    openai_api_key: SecretStr | None = None
    # "data/raw" (default, local disk) or "s3://bucket-name".
    raw_store: str = "data/raw"


def load_settings() -> Settings:
    """Read the settings from the environment.

    Raises:
        pydantic.ValidationError: if a required variable is missing or empty.
    """
    # Pyright strict does not know BaseSettings fills database_url from the environment.
    return Settings()  # pyright: ignore[reportCallIssue]
