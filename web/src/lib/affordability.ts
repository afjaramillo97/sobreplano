/**
 * "¿Me alcanza?" for one price (SPEC 11d §6), shared by the project page and the comparison.
 *
 * The two limits are the calculator's: the down payment against the savings, and the price
 * against what the income allows (finance.ts). A price can break both, and then both are said:
 * naming only one would read as if solving it were enough.
 */
import {
  type DecimalInput,
  downPaymentPlan,
  maxAffordablePrice,
  type MortgageSimulation,
  simulateMortgage,
} from "./finance";

export type FitInput = {
  incomeCop: number;
  savingsCop: number;
  rateEaPct: DecimalInput;
  years: number;
  downPaymentPct: number;
  monthsToDelivery: number | null;
};

export type ProjectFit = {
  /** Neither limit is broken. */
  fits: boolean;
  /** The loan for this price with the chosen down payment. */
  mortgage: MortgageSimulation;
  /** The monthly payment over the income, in percent. */
  paymentSharePct: number;
  /** Whether the income does not allow this price (the 40 % cap). */
  overIncome: boolean;
  /** Down payment the savings do not cover; 0 when they do. */
  missingCop: number;
  /** What the missing down payment takes each month of construction; null without months. */
  installment: { cop: number; incomeSharePct: number; months: number } | null;
};

/** Throws FinanceInputError with inputs out of range, a price of 0 included. */
export function projectFit(input: FitInput, priceCop: number): ProjectFit {
  const { incomeCop, savingsCop, downPaymentPct, monthsToDelivery: months } = input;
  const mortgage = simulateMortgage({ ...input, priceCop });
  const { maxPriceByIncomeCop } = maxAffordablePrice({ ...input, monthlyIncomeCop: incomeCop });
  const overIncome = priceCop > maxPriceByIncomeCop;
  const missingCop = Math.max(0, mortgage.downPaymentCop - savingsCop);
  let installment: ProjectFit["installment"] = null;
  if (missingCop > 0 && months !== null) {
    const plan = downPaymentPlan({ priceCop, downPaymentPct, months, upfrontCop: savingsCop });
    const cop = plan.monthlyInstallmentCop;
    installment = { cop, incomeSharePct: (cop / incomeCop) * 100, months };
  }
  return {
    fits: !overIncome && missingCop === 0,
    mortgage,
    paymentSharePct: (mortgage.monthlyPaymentCop / incomeCop) * 100,
    overIncome,
    missingCop,
    installment,
  };
}
