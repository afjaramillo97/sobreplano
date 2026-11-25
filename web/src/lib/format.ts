/**
 * Number and date formats for the site, in Colombian Spanish (es-CO).
 *
 * Exact outputs, hard spaces included, are pinned in tests/unit/format.test.ts.
 */

const NBSP = " ";
// Typographic minus: the hyphen Intl puts in front of negative numbers reads as a dash.
const MINUS = "−";
// ICU's short month names vary by engine and version ("sep", "sept."), so they are fixed here.
const MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

const cop = new Intl.NumberFormat("es-CO", {
  style: "currency",
  currency: "COP",
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
});
const millions = new Intl.NumberFormat("es-CO", { maximumFractionDigits: 1 });
const percent = new Intl.NumberFormat("es-CO", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
  signDisplay: "exceptZero",
});
const area = new Intl.NumberFormat("es-CO", { maximumFractionDigits: 2 });
// API dates are days without a time; UTC keeps a browser west of Greenwich on the same day.
const dateParts = new Intl.DateTimeFormat("es-CO", {
  day: "numeric",
  month: "numeric",
  year: "numeric",
  timeZone: "UTC",
});
const dateShort = new Intl.DateTimeFormat("es-CO", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  timeZone: "UTC",
});

/** A price in pesos: 380000000 → "$ 380.000.000". */
export function formatCop(value: number): string {
  return cop.format(value);
}

/** A price in millions, one decimal at most: 445000000 → "$ 445 millones". */
export function formatMillions(value: number): string {
  return `$${NBSP}${millions.format(value / 1_000_000)}${NBSP}millones`;
}

/** A change in percent, as the API gives it (12.5 means 12.5 %): → "+12,5 %", "−3,0 %". */
export function formatPct(value: number): string {
  return `${percent.format(value).replace("-", MINUS)}${NBSP}%`;
}

/** An area in square meters: 58.5 → "58,5 m²". */
export function formatArea(value: number): string {
  return `${area.format(value)}${NBSP}m²`;
}

function toDate(iso: string): Date {
  if (!ISO_DATE.test(iso)) throw new Error(`not an ISO date (YYYY-MM-DD): ${iso}`);
  return new Date(`${iso}T00:00:00Z`);
}

/** A day for reading: "2026-11-02" → "2 nov 2026". */
export function formatDate(iso: string): string {
  const parts = dateParts.formatToParts(toDate(iso));
  const part = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((p) => p.type === type)?.value ?? "";
  const month = MONTHS[Number(part("month")) - 1];
  return `${part("day")} ${month} ${part("year")}`;
}

/** A day for tables: "2026-11-02" → "02/11/2026". */
export function formatDateShort(iso: string): string {
  return dateShort.format(toDate(iso));
}

/** A price change in words, for the badge: 9.8 → "Subió 9,8 %", −2.1 → "Bajó 2,1 %". */
export function formatChange(value: number): string {
  const magnitude = formatPct(Math.abs(value)).replace("+", "");
  if (value > 0) return `Subió ${magnitude}`;
  if (value < 0) return `Bajó ${magnitude}`;
  return "Sin cambio";
}

/** A count with its noun: (1, "alcoba", "alcobas") → "1 alcoba"; 2 → "2 alcobas". */
export function formatCount(value: number, singular: string, plural: string): string {
  return `${value}${NBSP}${value === 1 ? singular : plural}`;
}
