import { describe, expect, it } from "vitest";

import { calculate, type CalculatorInput } from "../../src/lib/calculator";
import { DEFAULT_SEARCH, type SearchItem, searchResults } from "../../src/lib/search";
import vectors from "../fixtures/finance-vectors.json";

// The calculator's acceptance case: the savings are the limit, at 200 million.
const INPUT: CalculatorInput = {
  incomeCop: 8_000_000,
  savingsCop: 60_000_000,
  rateEaPct: "15.45",
  years: 20,
  downPaymentPct: 30,
  monthsToDelivery: null,
};

function item(slug: string, ...prices: number[]): SearchItem {
  return {
    slug,
    name: slug,
    developer: { name: "Dev", slug: "dev" },
    municipality: "envigado",
    neighborhood: null,
    location: null,
    lastObservedOn: prices.length > 0 ? "2026-11-02" : null,
    units: prices.map((priceCop, i) => ({
      name: `Tipo ${i + 1}`,
      bedrooms: 2,
      bathrooms: 2,
      areaM2: 50,
      areaBasis: "private" as const,
      priceCop,
      changePct: null,
    })),
    searchText: slug,
  };
}

const ITEMS = [
  item("cara", 500_000_000),
  item("justa", 200_000_000, 300_000_000),
  item("barata", 150_000_000),
  item("sin-precio"),
  item("media", 250_000_000),
];

describe("the max price and its loan", () => {
  it("are the ones of Python", () => {
    const expected = vectors.affordability[0]!;
    const result = calculate(INPUT, ITEMS);
    expect(expected.input.monthlyIncomeCop).toBe(INPUT.incomeCop);
    expect(result.affordability).toEqual(expected.output);
    const loan = vectors.mortgage.find((c) => c.input.priceCop === expected.output.maxPriceCop)!;
    expect(result.mortgage).toEqual(loan.output);
    expect(result.paymentSharePct).toBeCloseTo((loan.output.monthlyPaymentCop / 8_000_000) * 100);
  });

  it("has no loan without savings", () => {
    const result = calculate({ ...INPUT, savingsCop: 0 }, ITEMS);
    expect(result.affordability.maxPriceCop).toBe(0);
    expect(result.mortgage).toBeNull();
    expect(result.paymentSharePct).toBeNull();
  });
});

describe("the months of construction", () => {
  const months = { ...INPUT, monthsToDelivery: 24 };

  it("say nothing without months", () => {
    expect(calculate(INPUT, ITEMS).construction).toBeNull();
  });

  it("show how far the income reaches when the savings are the limit", () => {
    const { construction, affordability } = calculate(months, ITEMS);
    expect(affordability.limitedBy).toBe("savings");
    expect(construction).toMatchObject({
      kind: "stretch",
      priceCop: 358_104_936,
      installmentCop: 1_976_312,
      months: 24,
    });
    expect(construction).toHaveProperty("incomeSharePct", (1_976_312 / 8_000_000) * 100);
  });

  it("stretch from nothing without savings", () => {
    const { construction } = calculate({ ...months, savingsCop: 0 }, ITEMS);
    expect(construction).toMatchObject({ kind: "stretch", priceCop: 358_104_936 });
  });

  it("are covered by the savings when the income is the limit", () => {
    const result = calculate({ ...months, savingsCop: 900_000_000 }, ITEMS);
    expect(result.affordability.limitedBy).toBe("income");
    expect(result.construction).toEqual({ kind: "covered" });
  });

  it("are covered when both limits give the same price", () => {
    const tie = { ...months, incomeCop: 6_000_000, savingsCop: 188_005_091, downPaymentPct: 50 };
    expect(calculate(tie, ITEMS).construction).toEqual({ kind: "covered" });
  });
});

describe("the projects", () => {
  it("count what the search shows up to the max price, the exact price included", () => {
    const result = calculate(INPUT, ITEMS);
    expect(result.matches).toBe(2);
    expect(result.matches).toBe(
      searchResults(ITEMS, { ...DEFAULT_SEARCH, priceMax: 200_000_000 }).length,
    );
    expect(result.cheapest).toEqual([]);
  });

  it("offer the three cheapest with what is missing when none fits", () => {
    const result = calculate({ ...INPUT, savingsCop: 30_000_000 }, ITEMS);
    expect(result.matches).toBe(0);
    expect(result.cheapest.map((p) => [p.slug, p.missingCop])).toEqual([
      ["barata", 50_000_000],
      ["justa", 100_000_000],
      ["media", 150_000_000],
    ]);
    expect(result.cheapest[0]).toMatchObject({ unitName: "Tipo 1", observedOn: "2026-11-02" });
  });
});
