import { describe, expect, it } from "vitest";
import { formatDayMonth, formatRetryAt } from "../../src/lib/format";
import {
  dailySeries,
  dayTicks,
  timeToDay,
  historySummary,
  isolatedDays,
  priceAxis,
  priceChanges,
} from "../../src/lib/history";

const NBSP = " ";
const p = (observedOn: string, priceCop: number) => ({ observedOn, priceCop });

describe("dailySeries", () => {
  it("has one point per day, null where nothing was observed", () => {
    const series = dailySeries([p("2026-11-04", 3), p("2026-11-01", 1), p("2026-11-02", 2)]);
    expect(series.map((d) => [d.day, d.priceCop])).toEqual([
      ["2026-11-01", 1],
      ["2026-11-02", 2],
      ["2026-11-03", null],
      ["2026-11-04", 3],
    ]);
    expect(series[1]!.t - series[0]!.t).toBe(24 * 60 * 60 * 1000);
  });

  it("is empty without prices", () => {
    expect(dailySeries([])).toEqual([]);
  });
});

describe("priceChanges", () => {
  it("keeps the first price and each day it changed, with the step change", () => {
    const rows = priceChanges([
      p("2026-07-01", 380_000_000),
      p("2026-07-02", 380_000_000),
      p("2026-07-20", 386_000_000),
      p("2026-08-01", 386_000_000),
      p("2026-09-01", 370_000_000),
    ]);
    expect(rows).toEqual([
      { observedOn: "2026-07-01", priceCop: 380_000_000, changePct: null },
      { observedOn: "2026-07-20", priceCop: 386_000_000, changePct: 1.6 },
      { observedOn: "2026-09-01", priceCop: 370_000_000, changePct: -4.1 },
    ]);
  });
});

describe("priceAxis", () => {
  it("cuts the axis to the prices, with the minimum and the maximum as ticks", () => {
    expect(priceAxis([p("2026-07-01", 400), p("2026-08-01", 500)])).toEqual({
      domain: [390, 510],
      ticks: [400, 500],
    });
  });

  it("keeps a flat history off the edges", () => {
    expect(priceAxis([p("2026-07-01", 500), p("2026-08-01", 500)])).toEqual({
      domain: [490, 510],
      ticks: [500],
    });
  });
});

describe("historySummary", () => {
  it("says the change and the dates, without repeating the year", () => {
    expect(historySummary([p("2026-09-07", 1), p("2026-11-02", 2)], 12.5)).toBe(
      `Subió 12,5${NBSP}% entre el 7 sep y el 2 nov 2026.`,
    );
  });

  it("keeps both years across a new year", () => {
    expect(historySummary([p("2025-12-20", 2), p("2026-01-10", 1)], -2.1)).toBe(
      `Bajó 2,1${NBSP}% entre el 20 dic 2025 y el 10 ene 2026.`,
    );
  });

  it("says so when there is a single day of prices", () => {
    expect(historySummary([p("2026-11-02", 1)], null)).toBe("Solo tenemos el precio del 2 nov 2026.");
  });
});

describe("isolatedDays", () => {
  it("finds the days with a price and no neighbour", () => {
    const series = dailySeries([p("2026-11-01", 1), p("2026-11-03", 2), p("2026-11-04", 2)]);
    expect([...isolatedDays(series)]).toEqual(["2026-11-01"]);
  });
});

describe("dayTicks", () => {
  it("marks the first day, each first of month and the last day", () => {
    const series = dailySeries([p("2026-07-20", 1), p("2026-09-07", 2)]);
    expect(dayTicks(series).map(timeToDay)).toEqual([
      "2026-07-20",
      "2026-08-01",
      "2026-09-01",
      "2026-09-07",
    ]);
  });
});

describe("formatDayMonth", () => {
  it("drops the year", () => {
    expect(formatDayMonth("2026-09-07")).toBe("7 sep");
  });
});

describe("formatRetryAt", () => {
  // vitest.config.ts runs in Bogotá.
  const now = new Date("2026-11-14T15:00:20Z"); // 10:00:20 a. m. in Bogotá

  it("gives the time when the limit lifts the same day", () => {
    expect(formatRetryAt(120, now)).toMatch(/^a las 10:02\sa.\s?m.$/);
  });

  it("says tomorrow when it lifts after midnight", () => {
    // 14 h later: 00:00:20 the next day in Bogotá.
    expect(formatRetryAt(14 * 3600, now)).toMatch(/^mañana a las 12:00\sa.\s?m.$/);
  });
});
