import { describe, expect, it } from "vitest";

import * as finance from "../../src/lib/finance";
import {
  downPaymentPlan,
  FinanceInputError,
  maxAffordablePrice,
  simulateMortgage,
} from "../../src/lib/finance";
import vectors from "../fixtures/finance-vectors.json";

// The Python names the vectors use for the functions.
const FUNCTIONS: Record<string, (input: never) => unknown> = {
  simulate_mortgage: simulateMortgage,
  max_affordable_price: maxAffordablePrice,
  down_payment_plan: downPaymentPlan,
};

const name = (input: object) => JSON.stringify(input);

describe("constants", () => {
  it("are the ones of finance.py", () => {
    for (const [key, value] of Object.entries(vectors.constants)) {
      expect(finance[key as keyof typeof vectors.constants], key).toBe(Number(value));
    }
  });
});

describe("simulateMortgage gives the pesos of Python", () => {
  it.each(vectors.mortgage.map((c) => [name(c.input), c] as const))("%s", (_, { input, output }) => {
    expect(simulateMortgage(input)).toEqual(output);
  });
});

describe("maxAffordablePrice gives the pesos of Python", () => {
  it.each(vectors.affordability.map((c) => [name(c.input), c] as const))(
    "%s",
    (_, { input, output }) => {
      expect(maxAffordablePrice(input)).toEqual(output);
    },
  );
});

describe("downPaymentPlan gives the pesos of Python", () => {
  it.each(vectors.downPaymentPlan.map((c) => [name(c.input), c] as const))(
    "%s",
    (_, { input, output }) => {
      expect(downPaymentPlan(input)).toEqual(output);
    },
  );
});

describe("inputs out of range", () => {
  it.each(vectors.errors.map((c) => [`${c.fn} ${name(c.input)}`, c] as const))(
    "%s",
    (_, { fn, input, code }) => {
      const call = () => FUNCTIONS[fn]!(input as never);
      expect(call).toThrow(FinanceInputError);
      expect(call).toThrow(expect.objectContaining({ code }));
    },
  );

  // A form field that is not a number must not reach the decimal library.
  it("rejects a value that is not a number with the code of its rule", () => {
    const valid = { priceCop: 380_000_000, rateEaPct: 15.45, years: 20, downPaymentPct: 30 };
    expect(() => simulateMortgage({ ...valid, priceCop: NaN })).toThrow("price-not-positive");
    expect(() => simulateMortgage({ ...valid, rateEaPct: NaN })).toThrow("rate-out-of-range");
    expect(() => simulateMortgage({ ...valid, years: NaN })).toThrow("years-out-of-range");
  });

  it("takes rates and percentages as numbers too", () => {
    const text = { priceCop: 380_000_000, rateEaPct: "15.45", years: 20, downPaymentPct: "30" };
    expect(simulateMortgage({ ...text, rateEaPct: 15.45, downPaymentPct: 30 })).toEqual(
      simulateMortgage(text),
    );
  });

  it("defaults the upfront of a down payment plan to zero", () => {
    const plan = downPaymentPlan({ priceCop: 380_000_000, downPaymentPct: 30, months: 24 });
    expect(plan.upfrontCop).toBe(0);
  });
});
