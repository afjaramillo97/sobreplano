"""Unit tests for the Lambda handler with a fake SSM client and a fake scrape runner."""

from collections.abc import Mapping, Sequence
from typing import Any

import pytest
from pydantic import ValidationError

from sobreplano.application.scrape_developer import ScrapeReport
from sobreplano.domain.scraping import ScrapeRunStatus
from sobreplano.infrastructure.settings import Settings
from sobreplano.interface.lambda_handler import (
    ScrapeEvent,
    ScrapeFailedError,
    handle,
    settings_from_ssm,
)

ENVIRON = {
    "SSM_DATABASE_URL": "/sobreplano/prod/database_url",
    "SSM_OPENAI_API_KEY": "/sobreplano/prod/openai_api_key",
}
URL = "postgresql+psycopg://postgres.ref:pw@aws-0-us-east-1.pooler.supabase.com:6543/postgres"


class FakeSsm:
    def __init__(self, values: Mapping[str, str]) -> None:
        self.values = values
        self.calls: list[tuple[list[str], bool]] = []

    def get_parameters(self, *, Names: Sequence[str], WithDecryption: bool) -> Mapping[str, Any]:
        self.calls.append((list(Names), WithDecryption))
        return {
            "Parameters": [{"Name": n, "Value": self.values[n]} for n in Names if n in self.values],
            "InvalidParameters": [n for n in Names if n not in self.values],
        }


class FakeRunner:
    def __init__(self, report: ScrapeReport) -> None:
        self.report = report
        self.events: list[ScrapeEvent] = []

    def __call__(self, settings: Settings, event: ScrapeEvent) -> ScrapeReport:
        self.events.append(event)
        return self.report


SETTINGS = Settings(database_url=URL)


def test_reads_both_secrets_in_one_decrypted_call() -> None:
    ssm = FakeSsm({"/sobreplano/prod/database_url": URL, "/sobreplano/prod/openai_api_key": "sk-x"})
    settings = settings_from_ssm(ssm, ENVIRON)
    assert ssm.calls == [(list(ENVIRON.values()), True)]
    assert settings.database_url == URL
    assert settings.openai_api_key is not None
    assert settings.openai_api_key.get_secret_value() == "sk-x"


def test_unknown_parameter_fails_loudly() -> None:
    with pytest.raises(RuntimeError, match="openai_api_key"):
        settings_from_ssm(FakeSsm({"/sobreplano/prod/database_url": URL}), ENVIRON)


def test_success_returns_the_report_as_json() -> None:
    runner = FakeRunner(ScrapeReport(status=ScrapeRunStatus.SUCCEEDED, observations_recorded=60))
    result = handle({"developer": "londono-gomez", "limit": None}, lambda: SETTINGS, runner)
    assert runner.events == [ScrapeEvent(developer="londono-gomez")]
    assert result["status"] == "succeeded"
    assert result["observations_recorded"] == 60


def test_failed_run_raises_so_lambda_counts_an_error() -> None:
    runner = FakeRunner(ScrapeReport(status=ScrapeRunStatus.FAILED, error="listing: 403"))
    with pytest.raises(ScrapeFailedError, match="listing: 403"):
        handle({"developer": "londono-gomez"}, lambda: SETTINGS, runner)


@pytest.mark.parametrize(
    "event",
    [
        {},
        {"developer": ""},
        {"developer": "londono-gomez", "limit": 0},
        {"developer": "x", "extra": 1},
    ],
)
def test_malformed_event_is_rejected_before_running(event: dict[str, Any]) -> None:
    runner = FakeRunner(ScrapeReport(status=ScrapeRunStatus.SUCCEEDED))

    def load() -> Settings:
        raise AssertionError("SSM must not be read for a malformed event")

    with pytest.raises(ValidationError):
        handle(event, load, runner)
    assert runner.events == []
