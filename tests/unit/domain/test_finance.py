"""Unit tests for the mortgage, affordability and down payment maths."""

from decimal import Decimal
from typing import Any

import pytest

from sobreplano.domain.errors import DomainValidationError
from sobreplano.domain.finance import (
    Affordability,
    MortgageSimulation,
    down_payment_plan,
    max_affordable_price,
    monthly_rate,
    simulate_mortgage,
)

RATE = Decimal(12)
THIRTY = Decimal(30)


def mortgage(**overrides: Any) -> MortgageSimulation:
    args: dict[str, Any] = {
        "price_cop": 400_000_000,
        "annual_rate_ea_pct": RATE,
        "years": 20,
        "down_payment_pct": THIRTY,
    }
    return simulate_mortgage(**{**args, **overrides})


def affordability(**overrides: Any) -> Affordability:
    args: dict[str, Any] = {
        "monthly_income_cop": 12_000_000,
        "savings_cop": 150_000_000,
        "annual_rate_ea_pct": RATE,
        "years": 20,
        "down_payment_pct": THIRTY,
    }
    return max_affordable_price(**{**args, **overrides})


def test_monthly_rate_compounds_back_to_the_annual_rate() -> None:
    assert abs((1 + monthly_rate(RATE)) ** 12 - Decimal("1.12")) < Decimal("1e-20")


def test_mortgage_fixed_example() -> None:
    sim = mortgage()
    assert sim.down_payment_cop == 120_000_000
    assert sim.loan_cop == 280_000_000
    assert sim.months == 240
    assert sim.monthly_payment_cop == 2_964_145
    assert sim.total_paid_cop == 711_394_800
    assert sim.total_interest_cop == 431_394_800
    assert sim.min_monthly_income_cop == 7_410_363


def test_affordability_gives_the_down_payment_and_loan_of_the_max_price() -> None:
    # Savings bind: 150 M is 30 % of 500 M, so the loan is the other 350 M. This is not
    # max_loan_cop, which is what the income alone could repay.
    result = affordability()
    assert (result.max_price_cop, result.limited_by) == (500_000_000, "savings")
    assert (result.down_payment_cop, result.loan_cop) == (150_000_000, 350_000_000)
    assert result.down_payment_cop + result.loan_cop == result.max_price_cop


def test_affordability_loan_when_income_binds() -> None:
    result = affordability(monthly_income_cop=5_000_000, savings_cop=900_000_000)
    assert result.limited_by == "income"
    assert result.loan_cop + result.down_payment_cop == result.max_price_cop
    # When income binds, the loan needed is the loan the income supports (within rounding).
    assert abs(result.loan_cop - result.max_loan_cop) <= 1


def test_payments_repay_the_loan_at_the_monthly_rate() -> None:
    sim = mortgage()
    rate = monthly_rate(RATE)
    balance = Decimal(sim.loan_cop)
    for _ in range(sim.months):
        balance = balance * (1 + rate) - sim.monthly_payment_cop
    # Rounding the payment moves it by at most half a peso; that error compounds to the end.
    max_drift = Decimal("0.5") * ((1 + rate) ** sim.months - 1) / rate
    assert abs(balance) <= max_drift


def test_affordability_fixed_example_limited_by_savings() -> None:
    result = affordability()
    assert result.max_monthly_payment_cop == 4_800_000
    assert result.max_loan_cop == 453_419_055
    assert result.max_price_by_income_cop == 647_741_507
    assert result.max_price_by_savings_cop == 500_000_000
    assert result.max_price_cop == 500_000_000
    assert result.limited_by == "savings"


def test_affordability_limited_by_income_when_savings_are_large() -> None:
    result = affordability(savings_cop=1_000_000_000)
    assert result.limited_by == "income"
    assert result.max_price_cop == result.max_price_by_income_cop


def test_affordable_price_is_consistent_with_the_mortgage() -> None:
    result = affordability(savings_cop=1_000_000_000)
    sim = mortgage(price_cop=result.max_price_cop)
    assert abs(sim.monthly_payment_cop - result.max_monthly_payment_cop) <= 1


def test_down_payment_plan_fixed_example() -> None:
    plan = down_payment_plan(
        400_000_000, down_payment_pct=THIRTY, months=24, upfront_cop=10_000_000
    )
    assert plan.down_payment_cop == 120_000_000
    assert plan.upfront_cop == 10_000_000
    assert plan.monthly_installment_cop == 4_583_333
    assert plan.loan_at_delivery_cop == 280_000_000


def test_down_payment_plan_upfront_defaults_to_zero() -> None:
    plan = down_payment_plan(400_000_000, down_payment_pct=THIRTY, months=24)
    assert plan.upfront_cop == 0
    assert plan.monthly_installment_cop == 5_000_000


@pytest.mark.parametrize(
    "overrides",
    [
        {"price_cop": 0},
        {"annual_rate_ea_pct": Decimal(0)},
        {"annual_rate_ea_pct": Decimal("40.01")},
        {"years": 4},
        {"years": 31},
        {"down_payment_pct": Decimal("19.99")},
        {"down_payment_pct": Decimal(100)},
    ],
)
def test_simulate_mortgage_rejects_out_of_range_values(overrides: dict[str, Any]) -> None:
    with pytest.raises(DomainValidationError):
        mortgage(**overrides)


@pytest.mark.parametrize(
    "overrides",
    [
        {"monthly_income_cop": 0},
        {"savings_cop": -1},
        {"annual_rate_ea_pct": Decimal(0)},
        {"years": 31},
        {"down_payment_pct": Decimal(19)},
    ],
)
def test_max_affordable_price_rejects_out_of_range_values(overrides: dict[str, Any]) -> None:
    with pytest.raises(DomainValidationError):
        affordability(**overrides)


@pytest.mark.parametrize(
    "overrides",
    [
        {"price_cop": 0},
        {"months": 0},
        {"months": 61},
        {"down_payment_pct": Decimal(10)},
        {"upfront_cop": -1},
        {"upfront_cop": 120_000_001},
    ],
)
def test_down_payment_plan_rejects_out_of_range_values(overrides: dict[str, Any]) -> None:
    args: dict[str, Any] = {
        "price_cop": 400_000_000,
        "down_payment_pct": THIRTY,
        "months": 24,
    }
    with pytest.raises(DomainValidationError):
        down_payment_plan(**{**args, **overrides})


def test_boundaries_are_accepted() -> None:
    assert mortgage(annual_rate_ea_pct=Decimal(40), years=5, down_payment_pct=Decimal(20))
    assert affordability(savings_cop=0).max_price_by_savings_cop == 0
    plan = down_payment_plan(
        400_000_000, down_payment_pct=THIRTY, months=60, upfront_cop=120_000_000
    )
    assert plan.monthly_installment_cop == 0
