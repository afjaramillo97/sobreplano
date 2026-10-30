"""Application settings read from the environment."""

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Environment-backed configuration; DATABASE_URL is required and non-empty."""

    database_url: str = Field(min_length=1)


def load_settings() -> Settings:
    """Read the settings from the environment.

    Raises:
        pydantic.ValidationError: if a required variable is missing or empty.
    """
    # Pyright strict does not know BaseSettings fills database_url from the environment.
    return Settings()  # pyright: ignore[reportCallIssue]
