/**
 * The reference mortgage rate (SPEC 11d §3): what banks lent for housing in the latest week,
 * from the Superfinanciera's open data (format 414), weighted by the amount disbursed.
 *
 * Read at build time only; the pages pass it to the islands. Whatever goes wrong with the live
 * source, the build uses the versioned data/reference-rate.json.
 *
 * No relative TypeScript imports here: `pnpm rate:update` runs this file with Node alone.
 */
import Decimal from "decimal.js-light";

import versioned from "../data/reference-rate.json" with { type: "json" };

export type ReferenceRate = {
  vis: { rateEaPct: number; loans: number };
  noVis: { rateEaPct: number; loans: number };
  /** ISO day: the end of the week the loans were disbursed in. */
  cutOff: string;
  /** ISO day of the query. */
  fetchedOn: string;
  source: string;
  sourceUrl: string;
};

const API_URL = "https://www.datos.gov.co/resource/qzsc-9esp.json";
const SOURCE =
  "Superintendencia Financiera de Colombia, datos abiertos (formato 414), CC BY-SA 4.0";
const SOURCE_URL = "https://www.datos.gov.co/d/qzsc-9esp";
// Pesos only: since 2023-09-29 the UVR rate leaves out the UVR variation, so it reads too low.
const PRODUCTS = {
  vis: "Adquisición de vivienda vis (colocación en pesos)",
  noVis: "Adquisición de vivienda no vis (colocación en pesos)",
} as const;

const MIN_RATE_PCT = 5;
const MAX_RATE_PCT = 30;
const MIN_LOANS = 50;
const MAX_AGE_DAYS = 45;
const TIMEOUT_MS = 15_000;
const DAY_MS = 24 * 60 * 60 * 1000;

/** Today as an ISO day in Colombia. */
export function todayInBogota(now: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "America/Bogota" }).format(now);
}

/**
 * One row per product and week: the sum of rate x amount, the amount and the loans, of the
 * banks (tipo_entidad 1). The latest week comes first, so two rows are enough.
 */
export function queryUrl(): string {
  const products = Object.values(PRODUCTS)
    .map((product) => `'${product}'`)
    .join(",");
  const params = new URLSearchParams({
    $select:
      "fecha_corte,producto_de_cr_dito," +
      "sum(tasa_efectiva_promedio*montos_desembolsados) as weighted," +
      "sum(montos_desembolsados) as amount,sum(numero_de_creditos) as loans",
    $where: `tipo_entidad='1' AND producto_de_cr_dito in(${products})`,
    $group: "fecha_corte,producto_de_cr_dito",
    $order: "fecha_corte DESC,producto_de_cr_dito",
    $limit: "2",
  });
  return `${API_URL}?${params}`;
}

type Row = Record<string, unknown>;

function isRow(value: unknown): value is Row {
  return typeof value === "object" && value !== null;
}

function positiveNumber(row: Row, column: string): Decimal {
  const raw = row[column];
  const value = typeof raw === "string" || typeof raw === "number" ? Number(raw) : NaN;
  if (!(value > 0)) throw new Error(`column ${column} is not a positive number: ${String(raw)}`);
  return new Decimal(raw as string | number);
}

/**
 * The rate from the rows of queryUrl, checked before the site shows it.
 *
 * Throws if the latest week lacks either product, if a column changed, if a rate is outside
 * 5-30 % EA or has fewer than 50 loans behind it, or if the week is 45 days old or more.
 * Both rates come from the same week or neither is used: they share one cut-off date.
 */
export function parseReferenceRate(rows: unknown, today: string): ReferenceRate {
  if (!Array.isArray(rows) || !rows.every(isRow)) throw new Error("the answer is not a list of rows");
  const cutOff = String(rows[0]?.["fecha_corte"] ?? "").slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(cutOff)) throw new Error("no rows with a cut-off date");
  const age = Math.round((Date.parse(today) - Date.parse(cutOff)) / DAY_MS);
  if (!(age < MAX_AGE_DAYS)) throw new Error(`the latest week (${cutOff}) is ${age} days old`);

  const read = (product: string) => {
    const row = rows.find(
      (r) =>
        r["producto_de_cr_dito"] === product && String(r["fecha_corte"]).startsWith(cutOff),
    );
    if (!row) throw new Error(`the week of ${cutOff} has no row for "${product}"`);
    const rateEaPct = positiveNumber(row, "weighted")
      .div(positiveNumber(row, "amount"))
      .toDecimalPlaces(2, Decimal.ROUND_HALF_UP)
      .toNumber();
    const loans = positiveNumber(row, "loans").toNumber();
    if (rateEaPct < MIN_RATE_PCT || rateEaPct > MAX_RATE_PCT) {
      throw new Error(`rate ${rateEaPct} % of "${product}" is outside 5-30 %`);
    }
    if (loans < MIN_LOANS) throw new Error(`only ${loans} loans of "${product}" that week`);
    return { rateEaPct, loans };
  };

  return {
    vis: read(PRODUCTS.vis),
    noVis: read(PRODUCTS.noVis),
    cutOff,
    fetchedOn: today,
    source: SOURCE,
    sourceUrl: SOURCE_URL,
  };
}

type Fetcher = (url: string, init?: RequestInit) => Promise<Response>;

type FetchOptions = { fetcher?: Fetcher; today?: string };

/** The rate as the open data has it now. Throws, with the reason, if it cannot be used. */
export async function fetchReferenceRate({
  fetcher = fetch,
  today = todayInBogota(),
}: FetchOptions = {}): Promise<ReferenceRate> {
  const response = await fetcher(queryUrl(), { signal: AbortSignal.timeout(TIMEOUT_MS) });
  if (!response.ok) throw new Error(`datos.gov.co answered ${response.status}`);
  return parseReferenceRate(await response.json(), today);
}

/**
 * The live rate when asked for, the versioned one otherwise or when the live one fails.
 * Never throws: a build must not depend on a third party.
 */
export async function loadReferenceRate({
  live,
  log = console.warn,
  ...options
}: FetchOptions & { live: boolean; log?: (message: string) => void }): Promise<ReferenceRate> {
  if (!live) return versioned;
  try {
    return await fetchReferenceRate(options);
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error);
    log(
      `reference rate: the live query failed (${reason}); ` +
        `using data/reference-rate.json, cut-off ${versioned.cutOff}`,
    );
    return versioned;
  }
}

let cached: Promise<ReferenceRate> | undefined;

/**
 * The rate of this build, read once. Live only with REFERENCE_RATE=live (the deployment); CI
 * and the tests leave it unset, so their screenshots do not change with the market.
 */
export function buildReferenceRate(): Promise<ReferenceRate> {
  cached ??= loadReferenceRate({ live: import.meta.env.REFERENCE_RATE === "live" });
  return cached;
}
