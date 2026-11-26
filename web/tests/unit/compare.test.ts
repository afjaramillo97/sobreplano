import { describe, expect, it } from "vitest";

import {
  type CompareItem,
  type CompareUnit,
  lowestPerM2,
  pricePerM2,
  toCompareItem,
} from "../../src/lib/compare";
import type { ProjectView, UnitTypeView } from "../../src/lib/projects";

const unit = (priceCop: number, privateAreaM2: number | null, builtAreaM2: number | null): CompareUnit => ({
  name: "Tipo",
  bedrooms: 2,
  bathrooms: 2,
  privateAreaM2,
  builtAreaM2,
  priceCop,
});

const item = (...units: CompareUnit[]) => ({ units }) as CompareItem;

describe("pricePerM2", () => {
  it("divides by the chosen area only", () => {
    const both = unit(380_000_000, 58.5, 64.2);
    expect(pricePerM2(both, "private")).toBe(6_495_726);
    expect(pricePerM2(both, "built")).toBe(5_919_003);
  });

  it("is null when that area is not reported: nothing is estimated", () => {
    expect(pricePerM2(unit(300_000_000, 50, null), "built")).toBeNull();
    expect(pricePerM2(unit(300_000_000, null, 60), "private")).toBeNull();
  });

  it("rounds a half to even, as the API does", () => {
    expect(pricePerM2(unit(5, 2, null), "private")).toBe(2);
    expect(pricePerM2(unit(7, 2, null), "private")).toBe(4);
  });
});

describe("lowestPerM2", () => {
  const items = [
    item(unit(300_000_000, 60, 66), unit(350_000_000, null, 100)),
    item(unit(400_000_000, 100, null)),
  ];

  it("is the lowest of every unit type with that area", () => {
    expect(lowestPerM2(items, "private")).toBe(4_000_000);
    expect(lowestPerM2(items, "built")).toBe(3_500_000);
  });

  it("is null when none reports it", () => {
    expect(lowestPerM2([item(unit(1, 1, null))], "built")).toBeNull();
  });
});

describe("toCompareItem", () => {
  const view = (name: string, priceCop: number | null, status: UnitTypeView["status"]) => ({
    name,
    bedrooms: 3,
    bathrooms: 2,
    privateAreaM2: 70,
    builtAreaM2: null,
    priceCop,
    observedOn: "2026-11-02",
    changePct: 4.2,
    firstPrice: { priceCop: 1, observedOn: "2026-07-01" },
    status,
  }) as UnitTypeView;
  const current = view("A", 300_000_000, "current");
  const project = {
    slug: "torre",
    name: "Torre",
    developer: { name: "Constructora", slug: "c" },
    municipality: "envigado",
    neighborhood: null,
    sourceUrl: "https://example.com",
    lastObservedOn: "2026-11-02",
    from: current,
    unitTypes: [current, view("B", null, "not-published")],
  } as unknown as ProjectView;

  it("keeps the current unit types and the change of the desde", () => {
    expect(toCompareItem(project)).toMatchObject({
      developer: "Constructora",
      from: { name: "A", priceCop: 300_000_000, observedOn: "2026-11-02" },
      changePct: 4.2,
      firstObservedOn: "2026-07-01",
      units: [{ name: "A", privateAreaM2: 70, builtAreaM2: null }],
    });
  });

  it("has no desde without a current price", () => {
    const unpriced = { ...project, from: null, unitTypes: [view("B", null, "no-price")] };
    expect(toCompareItem(unpriced)).toMatchObject({ from: null, changePct: null, units: [] });
  });
});
