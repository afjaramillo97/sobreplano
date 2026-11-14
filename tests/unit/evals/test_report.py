"""Unit tests for the shared report pieces: totals, cost cap, price check and file names."""

from datetime import date
from decimal import Decimal

import pytest

from sobreplano.domain.advisor import LlmCall
from sobreplano.evals.report import (
    CostCap,
    UnknownPriceError,
    UsageTotals,
    percent,
    report_stem,
    require_prices,
)


def call(cost: str | None) -> LlmCall:
    return LlmCall(
        model="m",
        input_tokens=10,
        output_tokens=2,
        cost_usd=None if cost is None else Decimal(cost),
        prompt_version=None,
    )


def test_usage_totals_count_unpriced_calls_apart() -> None:
    totals = UsageTotals()
    totals.add([call("0.01"), call(None), call("0.02")])
    assert (totals.calls, totals.input_tokens, totals.output_tokens) == (3, 30, 6)
    assert (totals.cost_usd, totals.unpriced_calls) == (Decimal("0.03"), 1)


def test_cost_cap_is_exceeded_only_above_the_maximum() -> None:
    cap = CostCap(Decimal("0.03"))
    cap.add([call("0.01"), call("0.02"), call(None)])
    assert not cap.exceeded
    cap.add([call("0.000001")])
    assert cap.exceeded


def test_unknown_price_needs_explicit_permission() -> None:
    require_prices(["openai:gpt-6-luna"], allow_unknown=False)
    with pytest.raises(UnknownPriceError, match="openai:mystery"):
        require_prices(["openai:gpt-6-luna", "openai:mystery"], allow_unknown=False)
    require_prices(["openai:mystery"], allow_unknown=True)


def test_report_stem_is_a_safe_file_name() -> None:
    stem = report_stem("extraction", "openrouter:qwen/qwen3.7-flash", date(2026, 11, 13))
    assert stem == "extraction-2026-11-13-openrouter_qwen_qwen3.7-flash"


def test_percent() -> None:
    assert (percent(9, 10), percent(0, 0)) == ("90.0 %", "n/a")
