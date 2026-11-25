/**
 * View model of a project, computed at build time from the API's ProjectOut.
 *
 * All price logic lives here (SPEC 11a §2), so components only format and lay out. Rules:
 * - A unit type is current when its last observation is from the project's latest day
 *   (docs/schema.md: one observation per unit type per day while it is published).
 * - A priced unit type observed before that day is "not-published": no current price, and it
 *   does not count for the "desde".
 * - "Desde" is the cheapest current unit type; the project's change is that unit type's.
 */
import type { Municipality, ProjectOut, UnitTypeOut } from "./api/client";

export type UnitTypeStatus = "current" | "not-published" | "no-price";

export type UnitTypeView = {
  id: string;
  name: string;
  bedrooms: number | null;
  bathrooms: number | null;
  /** Private area when known, built area otherwise. */
  areaM2: number;
  areaBasis: "private" | "built";
  /** Latest price, only while the unit type is current. */
  priceCop: number | null;
  /** Price per m² on areaBasis, only while the unit type is current. */
  pricePerM2Cop: number | null;
  /** ISO day of the last observation. */
  observedOn: string | null;
  firstPrice: { priceCop: number; observedOn: string } | null;
  /** As the API gives it, one decimal; null with a single day of prices. */
  changePct: number | null;
  status: UnitTypeStatus;
};

export type ProjectView = {
  slug: string;
  name: string;
  developer: { name: string; slug: string };
  municipality: Municipality;
  neighborhood: string | null;
  location: { lat: number; lon: number } | null;
  sourceUrl: string;
  /** The most recent observation among its unit types. */
  lastObservedOn: string | null;
  /** The cheapest current unit type. */
  from: UnitTypeView | null;
  /** Current ones first, by price; then the rest, by name. */
  unitTypes: UnitTypeView[];
};

/** Display names of the municipalities (the API sends slugs). */
export const MUNICIPALITY_NAMES: Record<Municipality, string> = {
  medellin: "Medellín",
  bello: "Bello",
  itagui: "Itagüí",
  envigado: "Envigado",
  sabaneta: "Sabaneta",
  la_estrella: "La Estrella",
  caldas: "Caldas",
  copacabana: "Copacabana",
  girardota: "Girardota",
  barbosa: "Barbosa",
};

const byName = (a: { name: string }, b: { name: string }) =>
  a.name.localeCompare(b.name, "es-CO", { numeric: true, sensitivity: "base" });

/** Current first, cheapest first (then by name); the rest by name. */
function compareUnitTypes(a: UnitTypeView, b: UnitTypeView): number {
  const aCurrent = a.priceCop !== null;
  const bCurrent = b.priceCop !== null;
  if (aCurrent !== bCurrent) return aCurrent ? -1 : 1;
  if (a.priceCop !== null && b.priceCop !== null && a.priceCop !== b.priceCop) {
    return a.priceCop - b.priceCop;
  }
  return byName(a, b);
}

/** The latest observation day among the unit types; ISO days compare as text. */
function latestDay(unitTypes: UnitTypeOut[]): string | null {
  let latest: string | null = null;
  for (const unit of unitTypes) {
    const day = unit.latest_price?.observed_on ?? null;
    if (day !== null && (latest === null || day > latest)) latest = day;
  }
  return latest;
}

/**
 * The view of one unit type, given its project's latest observation day.
 *
 * Throws if the unit type has no area: the schema requires one (docs/schema.md), so a missing
 * area means the contract broke, and the build should stop rather than show "0 m²".
 */
export function toUnitTypeView(unit: UnitTypeOut, lastObservedOn: string | null): UnitTypeView {
  const areaM2 = unit.private_area_m2 ?? unit.built_area_m2;
  if (areaM2 === null) throw new Error(`unit type ${unit.id} (${unit.name}) has no area`);
  const latest = unit.latest_price;
  const status: UnitTypeStatus =
    latest == null ? "no-price" : latest.observed_on === lastObservedOn ? "current" : "not-published";
  const current = status === "current";
  return {
    id: unit.id,
    name: unit.name,
    bedrooms: unit.bedrooms,
    bathrooms: unit.bathrooms,
    areaM2,
    areaBasis: unit.area_basis,
    priceCop: current && latest ? latest.price_cop : null,
    pricePerM2Cop: current ? unit.price_per_m2_cop : null,
    observedOn: latest?.observed_on ?? null,
    firstPrice: unit.first_price
      ? { priceCop: unit.first_price.price_cop, observedOn: unit.first_price.observed_on }
      : null,
    changePct: unit.change_since_first_pct,
    status,
  };
}

/**
 * The view of a project. Takes a ProjectOut and copies only its fields, so a detail with
 * history passed by mistake still leaves the history out of the static site.
 */
export function toProjectView(project: ProjectOut): ProjectView {
  const lastObservedOn = latestDay(project.unit_types);
  const unitTypes = project.unit_types
    .map((unit) => toUnitTypeView(unit, lastObservedOn))
    .sort(compareUnitTypes);
  const first = unitTypes[0];
  return {
    slug: project.slug,
    name: project.name,
    developer: { name: project.developer.name, slug: project.developer.slug },
    municipality: project.municipality,
    neighborhood: project.neighborhood,
    location: project.location ? { lat: project.location.lat, lon: project.location.lon } : null,
    sourceUrl: project.source_url,
    lastObservedOn,
    // After the sort, a current unit type comes first if there is any.
    from: first?.status === "current" ? first : null,
    unitTypes,
  };
}
