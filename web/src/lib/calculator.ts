/**
 * What "¿Qué puedo comprar?" shows for one household (SPEC 11d §6): the max price, its loan,
 * what to pay during construction and which projects of the build's catalog fit.
 *
 * Pure, so the island only renders. The maths is finance.ts; the matching is the search's own
 * (search.ts), so the count on the button is the count the search shows.
 */
import {
  type Affordability,
  type DecimalInput,
  downPaymentPlan,
  maxAffordablePrice,
  type MortgageSimulation,
  simulateMortgage,
} from "./finance";
import { DEFAULT_SEARCH, type SearchItem, searchResults } from "./search";

export type CalculatorInput = {
  incomeCop: number;
  savingsCop: number;
  rateEaPct: DecimalInput;
  years: number;
  downPaymentPct: number;
  /** Null when the person did not say when the home is delivered. */
  monthsToDelivery: number | null;
};

/**
 * The months of construction. The max price needs no installments (the savings cover its down
 * payment by construction), so when the savings are the limit this says how far the income
 * reaches, and what paying the rest of that down payment would take each month.
 */
export type Construction =
  | { kind: "covered" }
  | {
      kind: "stretch";
      priceCop: number;
      installmentCop: number;
      /** The installment over the income, in percent. */
      incomeSharePct: number;
      months: number;
    };

/** A project above the max price, with what is missing to reach its "desde". */
export type NearProject = {
  slug: string;
  name: string;
  unitName: string;
  priceCop: number;
  observedOn: string | null;
  missingCop: number;
};

export type CalculatorResult = {
  affordability: Affordability;
  /** The loan for the max price; null when that price is 0, without savings. */
  mortgage: MortgageSimulation | null;
  /** The monthly payment over the income, in percent. */
  paymentSharePct: number | null;
  /** Null without months. */
  construction: Construction | null;
  /** Projects the search shows with precio_max at the max price. */
  matches: number;
  /** The three cheapest projects, only when none fits. */
  cheapest: NearProject[];
};

const CHEAPEST_SHOWN = 3;

function construction(input: CalculatorInput, result: Affordability): Construction | null {
  const { monthsToDelivery: months, downPaymentPct, savingsCop, incomeCop } = input;
  if (months === null) return null;
  const price = result.maxPriceByIncomeCop;
  if (result.limitedBy === "savings" && price > result.maxPriceCop) {
    const { downPaymentCop } = downPaymentPlan({ priceCop: price, downPaymentPct, months });
    const plan = downPaymentPlan({
      priceCop: price,
      downPaymentPct,
      months,
      upfrontCop: Math.min(savingsCop, downPaymentCop),
    });
    const installmentCop = plan.monthlyInstallmentCop;
    if (installmentCop > 0) {
      const incomeSharePct = (installmentCop / incomeCop) * 100;
      return { kind: "stretch", priceCop: price, installmentCop, incomeSharePct, months };
    }
  }
  return result.maxPriceCop > 0 ? { kind: "covered" } : null;
}

function cheapestAbove(items: readonly SearchItem[], maxPriceCop: number): NearProject[] {
  // The search's default order is the cheapest "desde" first, unpriced projects last.
  return searchResults(items, DEFAULT_SEARCH)
    .flatMap(({ item, from }) =>
      from === null
        ? []
        : [
            {
              slug: item.slug,
              name: item.name,
              unitName: from.name,
              priceCop: from.priceCop,
              observedOn: item.lastObservedOn,
              missingCop: from.priceCop - maxPriceCop,
            },
          ],
    )
    .slice(0, CHEAPEST_SHOWN);
}

/** Throws FinanceInputError with inputs out of range; the form validates them first. */
export function calculate(
  input: CalculatorInput,
  items: readonly SearchItem[],
): CalculatorResult {
  const affordability = maxAffordablePrice({ ...input, monthlyIncomeCop: input.incomeCop });
  const { maxPriceCop } = affordability;
  const mortgage = maxPriceCop > 0 ? simulateMortgage({ ...input, priceCop: maxPriceCop }) : null;
  const matches = searchResults(items, { ...DEFAULT_SEARCH, priceMax: maxPriceCop }).length;
  return {
    affordability,
    mortgage,
    paymentSharePct: mortgage ? (mortgage.monthlyPaymentCop / input.incomeCop) * 100 : null,
    construction: construction(input, affordability),
    matches,
    cheapest: matches === 0 ? cheapestAbove(items, maxPriceCop) : [],
  };
}
