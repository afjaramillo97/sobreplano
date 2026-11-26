import { describe, expect, it } from "vitest";

import { type FitInput, projectFit } from "../../src/lib/affordability";
import { maxAffordablePrice, simulateMortgage } from "../../src/lib/finance";

// At 15,45 % over 20 years: the income allows 358.104.936 and the savings 300.000.000.
const INPUT: FitInput = {
  incomeCop: 8_000_000,
  savingsCop: 90_000_000,
  rateEaPct: "15.45",
  years: 20,
  downPaymentPct: 30,
  monthsToDelivery: null,
};
const limits = maxAffordablePrice({ ...INPUT, monthlyIncomeCop: INPUT.incomeCop });

describe("a price within both limits", () => {
  it("fits, with its loan and the share of the income", () => {
    const fit = projectFit(INPUT, 236_000_000);
    expect(fit).toMatchObject({ fits: true, overIncome: false, missingCop: 0, installment: null });
    expect(fit.mortgage).toEqual(simulateMortgage({ ...INPUT, priceCop: 236_000_000 }));
    expect(fit.paymentSharePct).toBeCloseTo((fit.mortgage.monthlyPaymentCop / 8_000_000) * 100);
  });

  it("fits at exactly the max price", () => {
    expect(limits.maxPriceCop).toBe(300_000_000);
    expect(projectFit(INPUT, limits.maxPriceCop).fits).toBe(true);
    expect(projectFit(INPUT, limits.maxPriceCop + 10).fits).toBe(false);
  });
});

describe("a price above the savings", () => {
  it("says how much down payment is missing", () => {
    const fit = projectFit(INPUT, 340_000_000);
    expect(fit).toMatchObject({ fits: false, overIncome: false, missingCop: 12_000_000 });
    expect(fit.installment).toBeNull();
  });

  it("spreads it over the months of construction", () => {
    const fit = projectFit({ ...INPUT, monthsToDelivery: 24 }, 340_000_000);
    expect(fit.installment).toEqual({ cop: 500_000, incomeSharePct: 6.25, months: 24 });
  });
});

describe("a price above the income", () => {
  it("says so even when the savings cover the down payment", () => {
    const fit = projectFit({ ...INPUT, savingsCop: 150_000_000 }, 400_000_000);
    expect(fit).toMatchObject({ fits: false, overIncome: true, missingCop: 0 });
    expect(fit.paymentSharePct).toBeGreaterThan(40);
  });

  it("says both when both are broken", () => {
    const fit = projectFit(INPUT, 500_000_000);
    expect(fit).toMatchObject({ fits: false, overIncome: true, missingCop: 60_000_000 });
  });

  it("allows the highest price the income reaches", () => {
    const rich = { ...INPUT, savingsCop: 900_000_000 };
    expect(projectFit(rich, limits.maxPriceByIncomeCop).fits).toBe(true);
    expect(projectFit(rich, limits.maxPriceByIncomeCop + 1).overIncome).toBe(true);
  });
});
