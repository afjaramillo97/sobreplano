"""The vectors of the web port match finance.py: a changed formula needs finance_vectors again."""

import json
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path
from typing import Any

import pytest

from sobreplano.interface.cli import finance_vectors
from sobreplano.interface.cli.finance_vectors import VECTORS_PATH, main, render_vectors

RERUN = "run: uv run python -m sobreplano.interface.cli.finance_vectors"


def vectors() -> dict[str, Any]:
    return json.loads(render_vectors())


def test_the_vectors_in_the_repo_match_finance_py() -> None:
    assert VECTORS_PATH.exists(), RERUN
    assert VECTORS_PATH.read_text(encoding="utf-8") == render_vectors(), f"stale; {RERUN}"


def test_check_exits_zero_when_the_file_is_current() -> None:
    assert main(["--check"]) == 0


def test_check_exits_one_when_a_case_was_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    changed = vectors()
    changed["mortgage"][0]["output"]["monthlyPaymentCop"] += 1
    stale = tmp_path / "finance-vectors.json"
    stale.write_text(json.dumps(changed, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    monkeypatch.setattr(finance_vectors, "VECTORS_PATH", stale)
    assert main(["--check"]) == 1


def test_check_exits_one_when_the_file_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(finance_vectors, "VECTORS_PATH", tmp_path / "none.json")
    assert main(["--check"]) == 1


@pytest.mark.parametrize("section", ["mortgage", "affordability", "downPaymentPlan"])
def test_every_function_has_at_least_twenty_cases(section: str) -> None:
    assert len(vectors()[section]) >= 20


def test_the_cases_cover_both_limits_and_both_ends_of_the_ranges() -> None:
    data = vectors()
    assert {case["output"]["limitedBy"] for case in data["affordability"]} == {"income", "savings"}
    assert 0 in {case["input"]["savingsCop"] for case in data["affordability"]}
    inputs = [case["input"] for case in data["mortgage"]]
    assert {5, 30} <= {case["years"] for case in inputs}
    assert {"20", "99"} <= {case["downPaymentPct"] for case in inputs}
    assert {"0.01", "40"} <= {case["rateEaPct"] for case in inputs}
    assert {1, 60} <= {case["input"]["months"] for case in data["downPaymentPlan"]}


def test_a_case_tells_half_up_apart_from_half_even() -> None:
    # Without it a port using banker's rounding would pass every vector.
    assert any(
        int(exact.quantize(Decimal(1), rounding=ROUND_HALF_EVEN))
        != case["output"]["downPaymentCop"]
        for case in vectors()["mortgage"]
        for exact in [
            Decimal(case["input"]["priceCop"]) * Decimal(case["input"]["downPaymentPct"]) / 100
        ]
    )


def test_every_rule_has_an_error_case() -> None:
    assert {case["code"] for case in vectors()["errors"]} == {
        "price-not-positive",
        "rate-out-of-range",
        "years-out-of-range",
        "down-payment-out-of-range",
        "income-not-positive",
        "savings-negative",
        "months-out-of-range",
        "upfront-out-of-range",
    }
