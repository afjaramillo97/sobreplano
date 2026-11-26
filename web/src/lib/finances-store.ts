/**
 * The person's income, savings and loan settings in the browser (SPEC 11d §4): one versioned
 * localStorage key, shared by the calculator, "¿Me alcanza?" and the comparison.
 *
 * Income and savings never go in a URL nor in a request. "Olvidar mis datos" removes the key.
 */
import { readJson, removeKey, writeJson } from "./browser-storage";
import {
  defaultDownPaymentPct,
  maxPlanMonths,
  maxRateEaPct,
  maxYears,
  minDownPaymentPct,
  minYears,
} from "./finance";
import type { ReferenceRate } from "./reference-rate";

export const FINANCES_KEY = "sobreplano.finanzas.v1";
export const DEFAULT_YEARS = 20;

export type Housing = "vis" | "no-vis";

export type StoredFinances = {
  incomeCop: number | null;
  savingsCop: number | null;
  housing: Housing;
  monthsToDelivery: number | null;
  /** "reference" follows the rate of the build; "custom" is the one the person typed. */
  rate: { source: "reference" } | { source: "custom"; eaPct: number };
  years: number;
  downPaymentPct: number;
  /** ISO instant of the last save. */
  updatedAt: string;
};

export const EMPTY_FINANCES: StoredFinances = {
  incomeCop: null,
  savingsCop: null,
  // The API does not know which projects are VIS (SPEC 16), so the person chooses.
  housing: "no-vis",
  monthsToDelivery: null,
  rate: { source: "reference" },
  years: DEFAULT_YEARS,
  downPaymentPct: defaultDownPaymentPct,
  updatedAt: new Date(0).toISOString(),
};

/**
 * What was saved, or null when nothing was. A field that is missing or out of range takes its
 * default, so data written by another version still loads and cannot break the maths.
 */
export function readFinances(storage: Storage | null): StoredFinances | null {
  const data = readJson(storage, FINANCES_KEY);
  if (typeof data !== "object" || data === null || Array.isArray(data)) return null;
  const saved = data as Record<string, unknown>;
  return {
    incomeCop: integerIn(saved["incomeCop"], 1, Number.MAX_SAFE_INTEGER),
    savingsCop: integerIn(saved["savingsCop"], 0, Number.MAX_SAFE_INTEGER),
    housing: saved["housing"] === "vis" ? "vis" : "no-vis",
    monthsToDelivery: integerIn(saved["monthsToDelivery"], 1, maxPlanMonths),
    rate: readRate(saved["rate"]),
    years: integerIn(saved["years"], minYears, maxYears) ?? DEFAULT_YEARS,
    downPaymentPct: readDownPaymentPct(saved["downPaymentPct"]),
    updatedAt:
      typeof saved["updatedAt"] === "string" ? saved["updatedAt"] : EMPTY_FINANCES.updatedAt,
  };
}

/** Save, stamped with now; false when the storage is missing or full, so the page says so. */
export function writeFinances(
  storage: Storage | null,
  finances: StoredFinances,
  now: Date = new Date(),
): boolean {
  return writeJson(storage, FINANCES_KEY, { ...finances, updatedAt: now.toISOString() });
}

/** "Olvidar mis datos"; false when the storage could not be reached. */
export function clearFinances(storage: Storage | null): boolean {
  return removeKey(storage, FINANCES_KEY);
}

/** The rate the maths use: the person's own, or the reference one for VIS or not VIS. */
export function rateEaPct(finances: StoredFinances, reference: ReferenceRate): number {
  if (finances.rate.source === "custom") return finances.rate.eaPct;
  return (finances.housing === "vis" ? reference.vis : reference.noVis).rateEaPct;
}

function integerIn(value: unknown, min: number, max: number): number | null {
  return typeof value === "number" && Number.isInteger(value) && value >= min && value <= max
    ? value
    : null;
}

function readRate(value: unknown): StoredFinances["rate"] {
  if (typeof value === "object" && value !== null) {
    const { source, eaPct } = value as Record<string, unknown>;
    if (source === "custom" && typeof eaPct === "number" && eaPct > 0 && eaPct <= maxRateEaPct) {
      return { source: "custom", eaPct };
    }
  }
  return { source: "reference" };
}

function readDownPaymentPct(value: unknown): number {
  return typeof value === "number" && value >= minDownPaymentPct && value < 100
    ? value
    : defaultDownPaymentPct;
}
