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
const share = new Intl.NumberFormat("es-CO", { maximumFractionDigits: 1 });
const rate = new Intl.NumberFormat("es-CO", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
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

/**
 * A price in millions for tight places, the map pill and the filter chips: 289000000 →
 * "$ 289 M". Elsewhere use formatMillions, which spells the word out.
 */
export function formatMillionsShort(value: number): string {
  return `$${NBSP}${millions.format(value / 1_000_000)}${NBSP}M`;
}

/** A change in percent, as the API gives it (12.5 means 12.5 %): → "+12,5 %", "−3,0 %". */
export function formatPct(value: number): string {
  return `${percent.format(value).replace("-", MINUS)}${NBSP}%`;
}

/** A share of a whole, unsigned: 23.44 → "23,4 %". */
export function formatShare(value: number): string {
  return `${share.format(value)}${NBSP}%`;
}

/** An annual rate, always with two decimals: 15.4 → "15,40 %". */
export function formatRate(value: number): string {
  return `${rate.format(value)}${NBSP}%`;
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

/** A day without its year, for ranges inside one year: "2026-09-07" → "7 sep". */
export function formatDayMonth(iso: string): string {
  return formatDate(iso).replace(/ \d{4}$/, "");
}

const clock = new Intl.DateTimeFormat("es-CO", { hour: "numeric", minute: "2-digit" });
const DAY_MS = 24 * 60 * 60 * 1000;

/**
 * When a rate limit lifts, in the reader's local time: "a las 3:45 p. m.", or "mañana a las
 * 12:00 a. m." when it falls on the next day.
 */
export function formatRetryAt(retryAfterSeconds: number, now: Date = new Date()): string {
  const at = new Date(now.getTime() + retryAfterSeconds * 1000);
  const time = clock.format(at);
  const sameDay = at.toDateString() === now.toDateString();
  if (sameDay) return `a las ${time}`;
  const tomorrow = new Date(now.getTime() + DAY_MS).toDateString() === at.toDateString();
  return tomorrow ? `mañana a las ${time}` : `el ${formatDate(at.toISOString().slice(0, 10))}`;
}
