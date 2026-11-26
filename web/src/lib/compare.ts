/**
 * What the comparison shows of each project (SPEC 11d §5): the view the build hands the island
 * and the price per m² on one chosen area, private or built, never mixed nor estimated.
 */
import Decimal from "decimal.js-light";

import type { Municipality } from "./api/client";
import type { ProjectView } from "./projects";

export type AreaBasis = "private" | "built";

/** A current unit type: only those have a price to compare. */
export type CompareUnit = {
  name: string;
  bedrooms: number | null;
  bathrooms: number | null;
  privateAreaM2: number | null;
  builtAreaM2: number | null;
  priceCop: number;
};

export type CompareItem = {
  slug: string;
  name: string;
  developer: string;
  municipality: Municipality;
  neighborhood: string | null;
  lastObservedOn: string | null;
  /** The cheapest current unit type; null without a current price. */
  from: { name: string; priceCop: number; observedOn: string | null } | null;
  /** The change of the "desde" since its first price. */
  changePct: number | null;
  firstObservedOn: string | null;
  /** Current unit types, cheapest first. */
  units: CompareUnit[];
};

/** Copies only what the table shows: never the history, which stays out of the static site. */
export function toCompareItem(project: ProjectView): CompareItem {
  const { from } = project;
  const units: CompareUnit[] = [];
  for (const unit of project.unitTypes) {
    if (unit.status !== "current" || unit.priceCop === null) continue;
    units.push({
      name: unit.name,
      bedrooms: unit.bedrooms,
      bathrooms: unit.bathrooms,
      privateAreaM2: unit.privateAreaM2,
      builtAreaM2: unit.builtAreaM2,
      priceCop: unit.priceCop,
    });
  }
  return {
    slug: project.slug,
    name: project.name,
    developer: project.developer.name,
    municipality: project.municipality,
    neighborhood: project.neighborhood,
    lastObservedOn: project.lastObservedOn,
    from:
      from?.priceCop != null
        ? { name: from.name, priceCop: from.priceCop, observedOn: from.observedOn }
        : null,
    changePct: from?.changePct ?? null,
    firstObservedOn: from?.firstPrice?.observedOn ?? null,
    units,
  };
}

export function areaOf(unit: CompareUnit, basis: AreaBasis): number | null {
  return basis === "private" ? unit.privateAreaM2 : unit.builtAreaM2;
}

/**
 * Price over the chosen area, in whole pesos; null when that area is not reported. Half goes to
 * even, as the API rounds price_per_m2_cop (domain/listings.py), so the project page and this
 * table show the same figure.
 */
export function pricePerM2(unit: CompareUnit, basis: AreaBasis): number | null {
  const area = areaOf(unit, basis);
  if (area === null) return null;
  return new Decimal(unit.priceCop)
    .div(area)
    .toDecimalPlaces(0, Decimal.ROUND_HALF_EVEN)
    .toNumber();
}

/** The lowest price per m² among every unit type compared; null when none reports the area. */
export function lowestPerM2(items: readonly CompareItem[], basis: AreaBasis): number | null {
  const values = items.flatMap((item) =>
    item.units.flatMap((unit) => pricePerM2(unit, basis) ?? []),
  );
  return values.length > 0 ? Math.min(...values) : null;
}
