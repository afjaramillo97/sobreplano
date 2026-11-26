/**
 * Mortgage, affordability and down payment maths: the port of domain/finance.py (SPEC 11d §2).
 *
 * It must give the same pesos as Python: finance.test.ts runs it over the vectors that
 * finance_vectors writes. A change to the Python formulas is made here too. The maths runs in
 * decimals, never in floats, and rounds half up to whole pesos at the end.
 */
import Decimal from "decimal.js-light";

export const maxPaymentToIncome = 0.4; // Decreto 0583 de 2025: first payment <= 40 % of income
export const minDownPaymentPct = 20; // VIS is financed up to 80 %; the rest, up to 70 %
export const defaultDownPaymentPct = 30;
export const maxRateEaPct = 40;
export const minYears = 5; // Ley 546 de 1999
export const maxYears = 30;
export const maxPlanMonths = 60;

// Its own constructor, so no other user of the library changes these. 50 digits as in Python.
const Dec = Decimal.clone({ precision: 50, rounding: Decimal.ROUND_HALF_UP });

/** A rate or a percentage: "15.45" and 15.45 are the same value. */
export type DecimalInput = number | string;

/** Which rule an input broke; the UI writes its own message for each. */
export type FinanceErrorCode =
  | "price-not-positive"
  | "rate-out-of-range"
  | "years-out-of-range"
  | "down-payment-out-of-range"
  | "income-not-positive"
  | "savings-negative"
  | "months-out-of-range"
  | "upfront-out-of-range";

/** Thrown when an input is out of range. */
export class FinanceInputError extends Error {
  readonly code: FinanceErrorCode;

  constructor(code: FinanceErrorCode) {
    super(code);
    this.name = "FinanceInputError";
    this.code = code;
  }
}

/** Fixed-payment loan (French amortisation) for one price, without insurance. */
export type MortgageSimulation = {
  priceCop: number;
  downPaymentCop: number;
  loanCop: number;
  months: number;
  monthlyPaymentCop: number;
  /** Rounded payment times months. */
  totalPaidCop: number;
  totalInterestCop: number;
  /** Rounded payment / maxPaymentToIncome. */
  minMonthlyIncomeCop: number;
};

/** Highest price a household can reach, and which limit binds first. */
export type Affordability = {
  maxMonthlyPaymentCop: number;
  /** Present value of that payment over the term. */
  maxLoanCop: number;
  maxPriceByIncomeCop: number;
  maxPriceBySavingsCop: number;
  /** The lower of the two. */
  maxPriceCop: number;
  limitedBy: "income" | "savings";
  /** Down payment of maxPriceCop. */
  downPaymentCop: number;
  /** maxPriceCop minus that down payment: the loan actually needed. */
  loanCop: number;
};

/** Down payment spread over the construction months. */
export type DownPaymentPlan = {
  downPaymentCop: number;
  /** Reservation or first payment. */
  upfrontCop: number;
  months: number;
  monthlyInstallmentCop: number;
  loanAtDeliveryCop: number;
};

type LoanTerms = { rateEaPct: DecimalInput; years: number; downPaymentPct: DecimalInput };

function roundCop(value: Decimal): number {
  return value.toDecimalPlaces(0, Decimal.ROUND_HALF_UP).toNumber();
}

// The checks are written as "not inside the range", so that NaN fails them too.
function check(valid: boolean, code: FinanceErrorCode): void {
  if (!valid) throw new FinanceInputError(code);
}

function checkDownPaymentPct(downPaymentPct: DecimalInput): void {
  const pct = Number(downPaymentPct);
  check(pct >= minDownPaymentPct && pct < 100, "down-payment-out-of-range");
}

function checkLoanTerms({ rateEaPct, years, downPaymentPct }: LoanTerms): void {
  const rate = Number(rateEaPct);
  check(rate > 0 && rate <= maxRateEaPct, "rate-out-of-range");
  check(years >= minYears && years <= maxYears, "years-out-of-range");
  checkDownPaymentPct(downPaymentPct);
}

/** Payment per peso of loan: r / (1 - (1 + r) ** -n), with r the monthly equivalent rate. */
function paymentFactor(rateEaPct: DecimalInput, months: number): Decimal {
  const annual = new Dec(rateEaPct).div(100).plus(1);
  const rate = annual.pow(new Dec(1).div(12)).minus(1);
  return rate.div(new Dec(1).minus(rate.plus(1).pow(-months)));
}

/**
 * Fixed monthly payment for a price, a down payment, a rate and a term.
 *
 * Throws FinanceInputError if the price is not > 0, the rate is outside (0, 40] % EA, the term
 * is outside 5-30 years or the down payment is outside [20, 100) %.
 */
export function simulateMortgage(input: LoanTerms & { priceCop: number }): MortgageSimulation {
  const { priceCop, rateEaPct, years, downPaymentPct } = input;
  check(priceCop > 0, "price-not-positive");
  checkLoanTerms(input);
  const months = years * 12;
  const downPaymentCop = roundCop(new Dec(priceCop).times(downPaymentPct).div(100));
  const loanCop = priceCop - downPaymentCop;
  const monthlyPaymentCop = roundCop(new Dec(loanCop).times(paymentFactor(rateEaPct, months)));
  const totalPaidCop = monthlyPaymentCop * months;
  return {
    priceCop,
    downPaymentCop,
    loanCop,
    months,
    monthlyPaymentCop,
    totalPaidCop,
    totalInterestCop: totalPaidCop - loanCop,
    minMonthlyIncomeCop: roundCop(new Dec(monthlyPaymentCop).div(maxPaymentToIncome)),
  };
}

/**
 * Highest price allowed by the income (payment cap) and by the savings (down payment).
 *
 * Throws FinanceInputError if income is not > 0, savings is negative, or the rate, term or down
 * payment are out of range (see simulateMortgage).
 */
export function maxAffordablePrice(
  input: LoanTerms & { monthlyIncomeCop: number; savingsCop: number },
): Affordability {
  const { monthlyIncomeCop, savingsCop, rateEaPct, years, downPaymentPct } = input;
  check(monthlyIncomeCop > 0, "income-not-positive");
  check(savingsCop >= 0, "savings-negative");
  checkLoanTerms(input);
  const maxPayment = new Dec(monthlyIncomeCop).times(maxPaymentToIncome);
  const maxLoan = maxPayment.div(paymentFactor(rateEaPct, years * 12));
  const downFraction = new Dec(downPaymentPct).div(100);
  const byIncome = roundCop(maxLoan.div(new Dec(1).minus(downFraction)));
  const bySavings = roundCop(new Dec(savingsCop).div(downFraction));
  const maxPriceCop = Math.min(byIncome, bySavings);
  const downPaymentCop = roundCop(new Dec(maxPriceCop).times(downFraction));
  return {
    maxMonthlyPaymentCop: roundCop(maxPayment),
    maxLoanCop: roundCop(maxLoan),
    maxPriceByIncomeCop: byIncome,
    maxPriceBySavingsCop: bySavings,
    maxPriceCop,
    limitedBy: byIncome < bySavings ? "income" : "savings",
    downPaymentCop,
    loanCop: maxPriceCop - downPaymentCop,
  };
}

/**
 * Monthly installments of the down payment until delivery.
 *
 * Throws FinanceInputError if the price is not > 0, the down payment is outside [20, 100) %,
 * months are outside 1-60, or the upfront is outside [0, down payment].
 */
export function downPaymentPlan(input: {
  priceCop: number;
  downPaymentPct: DecimalInput;
  months: number;
  upfrontCop?: number;
}): DownPaymentPlan {
  const { priceCop, downPaymentPct, months, upfrontCop = 0 } = input;
  check(priceCop > 0, "price-not-positive");
  checkDownPaymentPct(downPaymentPct);
  check(months >= 1 && months <= maxPlanMonths, "months-out-of-range");
  const downPaymentCop = roundCop(new Dec(priceCop).times(downPaymentPct).div(100));
  check(upfrontCop >= 0 && upfrontCop <= downPaymentCop, "upfront-out-of-range");
  return {
    downPaymentCop,
    upfrontCop,
    months,
    monthlyInstallmentCop: roundCop(new Dec(downPaymentCop - upfrontCop).div(months)),
    loanAtDeliveryCop: priceCop - downPaymentCop,
  };
}
