"""Pure mortgage, affordability and off-plan down payment maths; no I/O, all in Decimal."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, localcontext
from typing import Literal

from sobreplano.domain.errors import DomainValidationError

MAX_PAYMENT_TO_INCOME = Decimal("0.40")  # Decreto 0583 de 2025: first payment <= 40 % of income
MIN_DOWN_PAYMENT_PCT = Decimal(20)  # VIS is financed up to 80 %; the rest, up to 70 %
DEFAULT_DOWN_PAYMENT_PCT = Decimal(30)
MAX_RATE_EA_PCT = Decimal(40)
MIN_YEARS, MAX_YEARS = 5, 30  # Ley 546 de 1999
MAX_PLAN_MONTHS = 60
_PRECISION = 50  # digits for the power and division steps; rounding to pesos happens at the end
_HUNDRED = Decimal(100)


@dataclass(frozen=True)
class MortgageSimulation:
    """Fixed-payment loan (French amortisation) for one price, without insurance."""

    price_cop: int
    down_payment_cop: int
    loan_cop: int
    months: int
    monthly_payment_cop: int
    total_paid_cop: int  # rounded payment times months
    total_interest_cop: int
    min_monthly_income_cop: int  # rounded payment / MAX_PAYMENT_TO_INCOME


@dataclass(frozen=True)
class Affordability:
    """Highest price a household can reach, and which limit binds first."""

    max_monthly_payment_cop: int
    max_loan_cop: int  # present value of that payment over the term
    max_price_by_income_cop: int
    max_price_by_savings_cop: int
    max_price_cop: int  # the lower of the two
    limited_by: Literal["income", "savings"]


@dataclass(frozen=True)
class DownPaymentPlan:
    """Down payment spread over the construction months."""

    down_payment_cop: int
    upfront_cop: int  # reservation or first payment
    months: int
    monthly_installment_cop: int
    loan_at_delivery_cop: int


def _round_cop(value: Decimal) -> int:
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _check_positive(name: str, value: int) -> None:
    if value <= 0:
        raise DomainValidationError(f"{name} must be > 0, got {value}")


def _check_loan_terms(annual_rate_ea_pct: Decimal, years: int, down_payment_pct: Decimal) -> None:
    if not 0 < annual_rate_ea_pct <= MAX_RATE_EA_PCT:
        raise DomainValidationError(
            f"annual_rate_ea_pct must be > 0 and <= {MAX_RATE_EA_PCT}, got {annual_rate_ea_pct}"
        )
    if not MIN_YEARS <= years <= MAX_YEARS:
        raise DomainValidationError(f"years must be between {MIN_YEARS} and {MAX_YEARS}")
    _check_down_payment_pct(down_payment_pct)


def _check_down_payment_pct(down_payment_pct: Decimal) -> None:
    if not MIN_DOWN_PAYMENT_PCT <= down_payment_pct < _HUNDRED:
        raise DomainValidationError(
            f"down_payment_pct must be >= {MIN_DOWN_PAYMENT_PCT} and < 100, got {down_payment_pct}"
        )


def monthly_rate(annual_rate_ea_pct: Decimal) -> Decimal:
    """Monthly rate equivalent to an effective annual one: (1 + EA) ** (1/12) - 1."""
    with localcontext() as ctx:
        ctx.prec = _PRECISION
        return (1 + annual_rate_ea_pct / _HUNDRED) ** (Decimal(1) / 12) - 1


def _payment_factor(rate: Decimal, months: int) -> Decimal:
    """Payment per peso of loan: r / (1 - (1 + r) ** -n). Needs prec set by the caller."""
    return rate / (1 - (1 + rate) ** -months)


def simulate_mortgage(
    price_cop: int, *, annual_rate_ea_pct: Decimal, years: int, down_payment_pct: Decimal
) -> MortgageSimulation:
    """Fixed monthly payment for a price, a down payment, a rate and a term.

    Raises:
        DomainValidationError: if the price is not > 0, the rate is outside (0, 40] % EA,
            the term is outside 5-30 years or the down payment is outside [20, 100) %.
    """
    _check_positive("price_cop", price_cop)
    _check_loan_terms(annual_rate_ea_pct, years, down_payment_pct)
    months = years * 12
    with localcontext() as ctx:
        ctx.prec = _PRECISION
        down_payment = _round_cop(Decimal(price_cop) * down_payment_pct / _HUNDRED)
        loan = price_cop - down_payment
        payment = _round_cop(
            Decimal(loan) * _payment_factor(monthly_rate(annual_rate_ea_pct), months)
        )
        min_income = _round_cop(Decimal(payment) / MAX_PAYMENT_TO_INCOME)
    total_paid = payment * months
    return MortgageSimulation(
        price_cop=price_cop,
        down_payment_cop=down_payment,
        loan_cop=loan,
        months=months,
        monthly_payment_cop=payment,
        total_paid_cop=total_paid,
        total_interest_cop=total_paid - loan,
        min_monthly_income_cop=min_income,
    )


def max_affordable_price(
    monthly_income_cop: int,
    savings_cop: int,
    *,
    annual_rate_ea_pct: Decimal,
    years: int,
    down_payment_pct: Decimal,
) -> Affordability:
    """Highest price allowed by the income (payment cap) and by the savings (down payment).

    Raises:
        DomainValidationError: if income is not > 0, savings is negative, or the rate, term
            or down payment are out of range (see simulate_mortgage).
    """
    _check_positive("monthly_income_cop", monthly_income_cop)
    if savings_cop < 0:
        raise DomainValidationError(f"savings_cop must be >= 0, got {savings_cop}")
    _check_loan_terms(annual_rate_ea_pct, years, down_payment_pct)
    months = years * 12
    with localcontext() as ctx:
        ctx.prec = _PRECISION
        max_payment = Decimal(monthly_income_cop) * MAX_PAYMENT_TO_INCOME
        max_loan = max_payment / _payment_factor(monthly_rate(annual_rate_ea_pct), months)
        down_fraction = down_payment_pct / _HUNDRED
        by_income = _round_cop(max_loan / (1 - down_fraction))
        by_savings = _round_cop(Decimal(savings_cop) / down_fraction)
        max_payment_cop = _round_cop(max_payment)
        max_loan_cop = _round_cop(max_loan)
    limited_by: Literal["income", "savings"] = "income" if by_income < by_savings else "savings"
    return Affordability(
        max_monthly_payment_cop=max_payment_cop,
        max_loan_cop=max_loan_cop,
        max_price_by_income_cop=by_income,
        max_price_by_savings_cop=by_savings,
        max_price_cop=min(by_income, by_savings),
        limited_by=limited_by,
    )


def down_payment_plan(
    price_cop: int, *, down_payment_pct: Decimal, months: int, upfront_cop: int = 0
) -> DownPaymentPlan:
    """Monthly installments of the down payment until delivery.

    Raises:
        DomainValidationError: if the price is not > 0, the down payment is outside [20, 100) %,
            months are outside 1-60, or the upfront is outside [0, down payment].
    """
    _check_positive("price_cop", price_cop)
    _check_down_payment_pct(down_payment_pct)
    if not 1 <= months <= MAX_PLAN_MONTHS:
        raise DomainValidationError(f"months must be between 1 and {MAX_PLAN_MONTHS}")
    down_payment = _round_cop(Decimal(price_cop) * down_payment_pct / _HUNDRED)
    if not 0 <= upfront_cop <= down_payment:
        raise DomainValidationError(
            f"upfront_cop must be between 0 and the down payment ({down_payment}), "
            f"got {upfront_cop}"
        )
    return DownPaymentPlan(
        down_payment_cop=down_payment,
        upfront_cop=upfront_cop,
        months=months,
        monthly_installment_cop=_round_cop(Decimal(down_payment - upfront_cop) / months),
        loan_at_delivery_cop=price_cop - down_payment,
    )
