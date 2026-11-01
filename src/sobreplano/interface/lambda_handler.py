"""AWS Lambda entry point: reads the secrets from SSM and scrapes one developer per event."""

import functools
import logging
import os
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol

import boto3
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from sobreplano.application.scrape_developer import ScrapeReport
from sobreplano.domain.scraping import ScrapeRunStatus
from sobreplano.infrastructure.settings import Settings
from sobreplano.interface.composition import format_summary, run_scrape

# Environment variables holding the SSM parameter names (set by Terraform), never the values.
SSM_DATABASE_URL = "SSM_DATABASE_URL"
SSM_OPENAI_API_KEY = "SSM_OPENAI_API_KEY"

logger = logging.getLogger(__name__)


class ScrapeEvent(BaseModel):
    """The event the scheduler sends: {"developer": "londono-gomez", "limit": null}."""

    model_config = ConfigDict(extra="forbid")

    developer: str = Field(min_length=1)
    limit: int | None = Field(default=None, ge=1)


class ScrapeFailedError(RuntimeError):
    """The run ended as failed; raised so Lambda counts an error, the alarm fires and the
    scheduler retries (safe: a run is idempotent within the day)."""


class SsmClient(Protocol):
    """The one boto3 SSM client method the handler needs, so tests can pass a fake."""

    def get_parameters(
        self, *, Names: Sequence[str], WithDecryption: bool
    ) -> Mapping[str, Any]: ...


ScrapeRunner = Callable[[Settings, ScrapeEvent], ScrapeReport]

_REPORT = TypeAdapter(ScrapeReport)


def settings_from_ssm(client: SsmClient, environ: Mapping[str, str]) -> Settings:
    """Read DATABASE_URL and OPENAI_API_KEY from SSM in one decrypted call.

    The other settings (EXTRACTION_MODEL, RAW_STORE) still come from the environment.

    Raises:
        KeyError: if SSM_DATABASE_URL or SSM_OPENAI_API_KEY is not set.
        RuntimeError: if SSM does not know one of the parameter names.
    """
    database_url_name = environ[SSM_DATABASE_URL]
    openai_api_key_name = environ[SSM_OPENAI_API_KEY]
    response = client.get_parameters(
        Names=[database_url_name, openai_api_key_name], WithDecryption=True
    )
    if response.get("InvalidParameters"):
        raise RuntimeError(f"unknown SSM parameters: {response['InvalidParameters']}")
    values = {parameter["Name"]: parameter["Value"] for parameter in response["Parameters"]}
    return Settings(
        database_url=values[database_url_name], openai_api_key=values[openai_api_key_name]
    )


def handle(
    raw_event: Mapping[str, Any], load: Callable[[], Settings], runner: ScrapeRunner
) -> dict[str, Any]:
    """Validate the event, load the settings, run the scrape and return the report as JSON.

    The event is validated first, so a malformed one never reaches SSM.

    Raises:
        pydantic.ValidationError: if the event is malformed.
        ScrapeFailedError: if the run failed (a skipped run is not an error).
    """
    event = ScrapeEvent.model_validate(raw_event)
    settings = load()
    report = runner(settings, event)
    logger.info(
        "%s\n%s", event.developer, format_summary(report, settings.extraction_model, dry_run=False)
    )
    if report.status is ScrapeRunStatus.FAILED:
        raise ScrapeFailedError(f"{event.developer}: run {report.status}: {report.error}")
    return _REPORT.dump_python(report, mode="json")


def _run(settings: Settings, event: ScrapeEvent) -> ScrapeReport:
    # NullPool: a pooled connection would outlive the invocation in a frozen Lambda.
    return run_scrape(settings, event.developer, limit=event.limit, dry_run=False, null_pool=True)


@functools.cache
def _cold_start_settings() -> Settings:
    # Once per container: warm invocations reuse the secrets instead of calling SSM again.
    client: SsmClient = boto3.client("ssm")  # pyright: ignore[reportUnknownMemberType]
    return settings_from_ssm(client, os.environ)


def handler(event: Mapping[str, Any], context: object) -> dict[str, Any]:
    """Lambda entry point (sobreplano.interface.lambda_handler.handler)."""
    return handle(event, _cold_start_settings, _run)


# The Lambda runtime installs its own handler on the root logger; only the levels change.
logging.getLogger().setLevel(logging.INFO)
for _noisy in ("httpx", "httpx2", "openai", "botocore", "boto3", "urllib3"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)
