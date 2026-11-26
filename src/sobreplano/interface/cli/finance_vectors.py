"""Write finance.py's results for fixed inputs, the test vectors of the web port (SPEC 11d)."""

import argparse
import dataclasses
import json
from collections.abc import Callable, Sequence
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sobreplano.domain import finance
from sobreplano.domain.errors import DomainValidationError

if TYPE_CHECKING:
    from _typeshed import DataclassInstance

# src/sobreplano/interface/cli/finance_vectors.py → the repository root.
REPO_ROOT = Path(__file__).resolve().parents[4]
VECTORS_PATH = REPO_ROOT / "web" / "tests" / "fixtures" / "finance-vectors.json"

# Inputs are named as the web port names them; decimals travel as strings so nothing is a float.
Inputs = dict[str, int | str]

# (price, rate % EA, years, down payment %)
MORTGAGE_CASES: tuple[tuple[int, str, int, str], ...] = (
    # The max price of the calculator's acceptance case, whose payment it shows.
    (200_000_000, "15.45", 20, "30"),
    # Prices of the fictitious catalog, at the reference rates.
    (236_000_000, "15.45", 20, "30"),
    (289_000_000, "15.45", 20, "30"),
    (289_900_000, "15.45", 20, "30"),
    (380_000_000, "14.57", 20, "30"),
    (427_600_000, "15.45", 15, "30"),
    (510_000_000, "15.45", 20, "40"),
    (890_000_000, "15.45", 10, "30"),
    (1_250_000_000, "15.45", 20, "30"),
    # Edges of each range.
    (380_000_000, "15.45", 20, "20"),
    (380_000_000, "15.45", 20, "99"),
    (380_000_000, "15.45", 5, "30"),
    (380_000_000, "15.45", 30, "30"),
    (380_000_000, "0.01", 20, "30"),
    (380_000_000, "40", 20, "30"),
    (1_250_000_000, "40", 30, "20"),
    (236_000_000, "0.01", 5, "99"),
    # The down payment lands exactly on ,5: half-up gives 50.000.001, half-even would not.
    (100_000_001, "12", 20, "50"),
    # Decimals in the rate and the down payment.
    (412_000_000, "13.275", 18, "33.33"),
    (520_000_000, "14.52", 25, "20.5"),
    # Odd monthly payments make the minimum income (payment x 2.5) land on ,5.
    (350_000_000, "12", 20, "30"),
    (5_000_000_000, "15.45", 30, "30"),
    # So small that the payment rounds to zero.
    (1, "15.45", 20, "30"),
)

# (monthly income, savings, rate % EA, years, down payment %)
AFFORDABILITY_CASES: tuple[tuple[int, int, str, int, str], ...] = (
    # The calculator's acceptance case, at both reference rates.
    (8_000_000, 60_000_000, "15.45", 20, "30"),
    (8_000_000, 60_000_000, "14.57", 20, "30"),
    # Income binds.
    (3_000_000, 900_000_000, "15.45", 20, "30"),
    (5_000_000, 900_000_000, "15.45", 20, "30"),
    (12_000_000, 500_000_000, "15.45", 15, "30"),
    # Savings bind.
    (20_000_000, 10_000_000, "15.45", 20, "30"),
    (12_000_000, 150_000_000, "12", 20, "30"),
    (30_000_000, 76_000_000, "14.57", 20, "20"),
    (8_000_000, 0, "15.45", 20, "30"),
    # Both limits give the same price: the tie counts as savings.
    (6_000_000, 188_005_091, "15.45", 20, "50"),
    # Savings / 40 % lands exactly on ,5.
    (20_000_000, 100_000_001, "15.45", 20, "40"),
    # Edges of each range.
    (8_000_000, 60_000_000, "15.45", 5, "30"),
    (8_000_000, 60_000_000, "15.45", 30, "30"),
    (8_000_000, 900_000_000, "0.01", 20, "30"),
    (8_000_000, 900_000_000, "40", 20, "30"),
    (8_000_000, 900_000_000, "15.45", 20, "20"),
    (8_000_000, 900_000_000, "15.45", 20, "99"),
    # Decimals, small and large amounts.
    (4_700_000, 55_500_000, "13.275", 18, "33.33"),
    (6_350_001, 95_000_000, "14.52", 25, "20.5"),
    (1_423_500, 20_000_000, "14.57", 20, "30"),
    (100_000_000, 3_000_000_000, "15.45", 30, "30"),
    (1, 1, "15.45", 20, "30"),
)

# (price, down payment %, months, upfront)
PLAN_CASES: tuple[tuple[int, str, int, int], ...] = (
    (236_000_000, "30", 18, 0),
    (289_000_000, "30", 24, 10_000_000),
    (289_900_000, "30", 30, 20_000_000),
    (380_000_000, "30", 36, 60_000_000),
    (427_600_000, "30", 24, 5_000_000),
    (510_000_000, "20", 12, 0),
    (890_000_000, "30", 48, 100_000_000),
    (1_250_000_000, "30", 60, 150_000_000),
    # Edges of each range.
    (380_000_000, "30", 1, 0),
    (380_000_000, "30", 60, 0),
    (380_000_000, "20", 24, 0),
    (380_000_000, "99", 24, 0),
    # The upfront covers the whole down payment: nothing left each month.
    (380_000_000, "30", 24, 114_000_000),
    # The down payment lands exactly on ,5.
    (100_000_001, "50", 10, 0),
    # The monthly installment lands exactly on ,5.
    (100_000_010, "50", 2, 0),
    (400_000_000, "30", 16, 1),
    # Decimals, small and large amounts.
    (412_000_000, "33.33", 27, 12_345_678),
    (520_000_000, "20.5", 33, 0),
    (381_000_000, "30", 7, 0),
    (5_000_000_000, "30", 60, 0),
    (10, "30", 3, 0),
    (1, "30", 1, 0),
)

_VALID_MORTGAGE: Inputs = {
    "priceCop": 380_000_000,
    "rateEaPct": "15.45",
    "years": 20,
    "downPaymentPct": "30",
}
_VALID_AFFORDABILITY: Inputs = {
    "monthlyIncomeCop": 8_000_000,
    "savingsCop": 60_000_000,
    "rateEaPct": "15.45",
    "years": 20,
    "downPaymentPct": "30",
}
_VALID_PLAN: Inputs = {
    "priceCop": 380_000_000,
    "downPaymentPct": "30",
    "months": 24,
    "upfrontCop": 0,
}


def _mortgage_inputs(case: tuple[int, str, int, str]) -> Inputs:
    price, rate, years, down = case
    return {"priceCop": price, "rateEaPct": rate, "years": years, "downPaymentPct": down}


def _affordability_inputs(case: tuple[int, int, str, int, str]) -> Inputs:
    income, savings, rate, years, down = case
    return {
        "monthlyIncomeCop": income,
        "savingsCop": savings,
        "rateEaPct": rate,
        "years": years,
        "downPaymentPct": down,
    }


def _plan_inputs(case: tuple[int, str, int, int]) -> Inputs:
    price, down, months, upfront = case
    return {"priceCop": price, "downPaymentPct": down, "months": months, "upfrontCop": upfront}


def _simulate_mortgage(inputs: Inputs) -> finance.MortgageSimulation:
    return finance.simulate_mortgage(
        int(inputs["priceCop"]),
        annual_rate_ea_pct=Decimal(inputs["rateEaPct"]),
        years=int(inputs["years"]),
        down_payment_pct=Decimal(inputs["downPaymentPct"]),
    )


def _max_affordable_price(inputs: Inputs) -> finance.Affordability:
    return finance.max_affordable_price(
        int(inputs["monthlyIncomeCop"]),
        int(inputs["savingsCop"]),
        annual_rate_ea_pct=Decimal(inputs["rateEaPct"]),
        years=int(inputs["years"]),
        down_payment_pct=Decimal(inputs["downPaymentPct"]),
    )


def _down_payment_plan(inputs: Inputs) -> finance.DownPaymentPlan:
    return finance.down_payment_plan(
        int(inputs["priceCop"]),
        down_payment_pct=Decimal(inputs["downPaymentPct"]),
        months=int(inputs["months"]),
        upfront_cop=int(inputs["upfrontCop"]),
    )


_RUNNERS: dict[str, Callable[[Inputs], "DataclassInstance"]] = {
    "simulate_mortgage": _simulate_mortgage,
    "max_affordable_price": _max_affordable_price,
    "down_payment_plan": _down_payment_plan,
}

# (rule code the port must raise, function, one input out of range over a valid base)
ERROR_CASES: tuple[tuple[str, str, Inputs], ...] = (
    ("price-not-positive", "simulate_mortgage", _VALID_MORTGAGE | {"priceCop": 0}),
    ("price-not-positive", "simulate_mortgage", _VALID_MORTGAGE | {"priceCop": -1}),
    ("rate-out-of-range", "simulate_mortgage", _VALID_MORTGAGE | {"rateEaPct": "0"}),
    ("rate-out-of-range", "simulate_mortgage", _VALID_MORTGAGE | {"rateEaPct": "40.01"}),
    ("years-out-of-range", "simulate_mortgage", _VALID_MORTGAGE | {"years": 4}),
    ("years-out-of-range", "simulate_mortgage", _VALID_MORTGAGE | {"years": 31}),
    (
        "down-payment-out-of-range",
        "simulate_mortgage",
        _VALID_MORTGAGE | {"downPaymentPct": "19.99"},
    ),
    ("down-payment-out-of-range", "simulate_mortgage", _VALID_MORTGAGE | {"downPaymentPct": "100"}),
    ("income-not-positive", "max_affordable_price", _VALID_AFFORDABILITY | {"monthlyIncomeCop": 0}),
    ("savings-negative", "max_affordable_price", _VALID_AFFORDABILITY | {"savingsCop": -1}),
    ("rate-out-of-range", "max_affordable_price", _VALID_AFFORDABILITY | {"rateEaPct": "40.01"}),
    ("years-out-of-range", "max_affordable_price", _VALID_AFFORDABILITY | {"years": 31}),
    (
        "down-payment-out-of-range",
        "max_affordable_price",
        _VALID_AFFORDABILITY | {"downPaymentPct": "19"},
    ),
    ("price-not-positive", "down_payment_plan", _VALID_PLAN | {"priceCop": 0}),
    ("down-payment-out-of-range", "down_payment_plan", _VALID_PLAN | {"downPaymentPct": "100"}),
    ("months-out-of-range", "down_payment_plan", _VALID_PLAN | {"months": 0}),
    ("months-out-of-range", "down_payment_plan", _VALID_PLAN | {"months": 61}),
    ("upfront-out-of-range", "down_payment_plan", _VALID_PLAN | {"upfrontCop": -1}),
    ("upfront-out-of-range", "down_payment_plan", _VALID_PLAN | {"upfrontCop": 114_000_001}),
)


def _camel(name: str) -> str:
    first, *rest = name.split("_")
    return first + "".join(word.capitalize() for word in rest)


def _case(fn: str, inputs: Inputs) -> dict[str, Any]:
    output = dataclasses.asdict(_RUNNERS[fn](inputs))
    return {"input": inputs, "output": {_camel(key): value for key, value in output.items()}}


def _error_case(code: str, fn: str, inputs: Inputs) -> dict[str, Any]:
    try:
        _RUNNERS[fn](inputs)
    except DomainValidationError as error:
        return {"fn": fn, "input": inputs, "code": code, "message": str(error)}
    raise ValueError(f"{fn} accepted an input that should fail with {code}: {inputs}")


def render_vectors() -> str:
    """The vectors as stable text: cases in the order written, indent 2, final newline.

    Raises:
        DomainValidationError: if a case meant to succeed has an input out of range.
        ValueError: if finance.py accepts a case meant to fail.
    """
    vectors = {
        "constants": {
            "maxPaymentToIncome": str(finance.MAX_PAYMENT_TO_INCOME),
            "minDownPaymentPct": str(finance.MIN_DOWN_PAYMENT_PCT),
            "maxRateEaPct": str(finance.MAX_RATE_EA_PCT),
            "minYears": finance.MIN_YEARS,
            "maxYears": finance.MAX_YEARS,
            "maxPlanMonths": finance.MAX_PLAN_MONTHS,
        },
        "mortgage": [_case("simulate_mortgage", _mortgage_inputs(case)) for case in MORTGAGE_CASES],
        "affordability": [
            _case("max_affordable_price", _affordability_inputs(case))
            for case in AFFORDABILITY_CASES
        ],
        "downPaymentPlan": [_case("down_payment_plan", _plan_inputs(case)) for case in PLAN_CASES],
        "errors": [_error_case(*case) for case in ERROR_CASES],
    }
    return json.dumps(vectors, indent=2, ensure_ascii=False) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    """Write the vectors; with --check, exit 1 if the file in the repo differs instead."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="compare with the file in the repo, write nothing"
    )
    args = parser.parse_args(argv)
    vectors = render_vectors()
    if args.check:
        current = VECTORS_PATH.read_text(encoding="utf-8") if VECTORS_PATH.exists() else None
        if current != vectors:
            print(f"{VECTORS_PATH} is out of date; run finance_vectors without --check")
            return 1
        print(f"{VECTORS_PATH} is up to date")
        return 0
    VECTORS_PATH.parent.mkdir(parents=True, exist_ok=True)
    VECTORS_PATH.write_text(vectors, encoding="utf-8")
    print(f"wrote {VECTORS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
