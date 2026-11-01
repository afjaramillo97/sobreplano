"""Unit tests for the scrape CLI: summary, cost estimate and argument checks."""

import pytest

from sobreplano.application.scrape_developer import ScrapeReport
from sobreplano.domain.scraping import ScrapeRunStatus
from sobreplano.infrastructure.scraping.providers import estimate_cost_usd
from sobreplano.interface.cli.scrape import main
from sobreplano.interface.composition import format_summary


def test_cost_uses_the_model_price_per_million_tokens() -> None:
    # 0.10 USD per million input and 0.50 per million output.
    assert estimate_cost_usd("openai:gpt-6-luna", 1_000_000, 200_000) == pytest.approx(0.20)


def test_cost_of_an_unknown_model_is_none() -> None:
    assert estimate_cost_usd("qwen:qwen3.7-flash", 1000, 100) is None


def test_summary_shows_counts_tokens_cost_and_failures() -> None:
    report = ScrapeReport(
        status=ScrapeRunStatus.SUCCEEDED,
        pages_listed=25,
        pages_fetched=23,
        pages_out_of_scope=1,
        pages_failed=1,
        unit_types_valid=60,
        unit_types_rejected=12,
        observations_recorded=60,
        extractions_new=23,
        input_tokens=40_000,
        output_tokens=8_000,
        failures=["https://x/node/1: refused"],
    )
    summary = format_summary(report, "openai:gpt-6-luna", dry_run=True)
    assert "status: succeeded (dry run, rolled back)" in summary
    assert "25 listed, 23 fetched, 1 out of scope, 1 failed" in summary
    assert "60 valid, 12 rejected" in summary
    assert "40000 input, 8000 output" in summary
    assert "estimated cost: 0.0080 USD" in summary
    assert "failed: https://x/node/1: refused" in summary


@pytest.mark.parametrize("argv", [["otra-constructora"], ["londono-gomez", "--limit", "0"]])
def test_bad_arguments_exit_before_touching_anything(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        main(argv)
    assert raised.value.code == 2


def test_summary_of_a_skipped_run_is_its_reason() -> None:
    report = ScrapeReport(status=ScrapeRunStatus.SKIPPED, error="a run already succeeded")
    assert format_summary(report, "openai:gpt-6-luna", dry_run=False) == (
        "status: skipped\nreason: a run already succeeded"
    )
