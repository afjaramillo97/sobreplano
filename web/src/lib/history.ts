/**
 * The price history of one unit type, ready for the chart and its table. Runs in the browser:
 * the history is fetched from GET /projects/{slug} and never goes into the static site.
 *
 * All the arithmetic lives here (SPEC 11a §2), so the island only lays it out.
 */
import { formatChange, formatDate, formatDayMonth } from "./format";

export type PricePoint = { priceCop: number; observedOn: string };

/** One day of the chart; null where nothing was observed, so the line breaks there. */
export type DailyPoint = { t: number; day: string; priceCop: number | null };

/** A row of the history table: a day the price changed (the first price included). */
export type PriceChange = PricePoint & { changePct: number | null };

const DAY_MS = 24 * 60 * 60 * 1000;
const dayToTime = (iso: string) => Date.parse(`${iso}T00:00:00Z`);

/** Oldest first; the API already sends them so, but the chart must not depend on it. */
export function sortPoints(points: PricePoint[]): PricePoint[] {
  return [...points].sort((a, b) => a.observedOn.localeCompare(b.observedOn));
}

/**
 * Every day from the first observation to the last, with its price or null. A day without an
 * observation is a gap: the chart does not invent a price for it (SPEC 11a §8).
 */
export function dailySeries(points: PricePoint[]): DailyPoint[] {
  const sorted = sortPoints(points);
  const first = sorted[0];
  const last = sorted.at(-1);
  if (!first || !last) return [];
  const byDay = new Map(sorted.map((p) => [p.observedOn, p.priceCop]));
  const series: DailyPoint[] = [];
  for (let t = dayToTime(first.observedOn); t <= dayToTime(last.observedOn); t += DAY_MS) {
    const day = new Date(t).toISOString().slice(0, 10);
    series.push({ t, day, priceCop: byDay.get(day) ?? null });
  }
  return series;
}

/** The days the price changed, with the change from the previous price (one decimal). */
export function priceChanges(points: PricePoint[]): PriceChange[] {
  const rows: PriceChange[] = [];
  for (const point of sortPoints(points)) {
    const previous = rows.at(-1);
    if (previous && previous.priceCop === point.priceCop) continue;
    const changePct = previous
      ? Math.round(((point.priceCop - previous.priceCop) / previous.priceCop) * 1000) / 10
      : null;
    rows.push({ ...point, changePct });
  }
  return rows;
}

/**
 * The Y axis, cut to the prices with a margin of 10 % of their range (2 % of the price when
 * flat), so a small rise is visible; its ticks are the minimum and the maximum.
 */
export function priceAxis(points: PricePoint[]): { domain: [number, number]; ticks: number[] } {
  const prices = points.map((p) => p.priceCop);
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const margin = max > min ? (max - min) * 0.1 : min * 0.02;
  return { domain: [min - margin, max + margin], ticks: max > min ? [min, max] : [min] };
}

/**
 * The chart's summary in words: "Subió 12,5 % entre el 7 sep y el 2 nov 2026".
 * `changePct` is the API's change since the first price, so the text and the badge agree.
 */
export function historySummary(points: PricePoint[], changePct: number | null): string {
  const sorted = sortPoints(points);
  const first = sorted[0];
  const last = sorted.at(-1);
  if (!first || !last) return "Sin precios publicados.";
  if (changePct === null || first.observedOn === last.observedOn) {
    return `Solo tenemos el precio del ${formatDate(first.observedOn)}.`;
  }
  const sameYear = first.observedOn.slice(0, 4) === last.observedOn.slice(0, 4);
  const from = sameYear ? formatDayMonth(first.observedOn) : formatDate(first.observedOn);
  return `${formatChange(changePct)} entre el ${from} y el ${formatDate(last.observedOn)}.`;
}

/** Days with a price whose neighbours have none: they get a dot, or they would not show. */
export function isolatedDays(series: DailyPoint[]): Set<string> {
  const isolated = new Set<string>();
  series.forEach((point, i) => {
    if (point.priceCop === null) return;
    const before = series[i - 1]?.priceCop ?? null;
    const after = series[i + 1]?.priceCop ?? null;
    if (before === null && after === null) isolated.add(point.day);
  });
  return isolated;
}

/** X axis ticks: the first day, the first of each month in between, and the last day. */
export function dayTicks(series: DailyPoint[]): number[] {
  const first = series[0];
  const last = series.at(-1);
  if (!first || !last) return [];
  const ticks = [first.t];
  for (const point of series) {
    if (point.day.endsWith("-01") && point.t !== first.t && point.t !== last.t) ticks.push(point.t);
  }
  if (last.t !== first.t) ticks.push(last.t);
  return ticks;
}

/** The ISO day of a chart time. */
export function timeToDay(t: number): string {
  return new Date(t).toISOString().slice(0, 10);
}
