import { describe, expect, it } from "vitest";
import {
  formatArea,
  formatChange,
  formatCount,
  formatCop,
  formatDate,
  formatDateShort,
  formatMillions,
  formatMillionsShort,
  formatPct,
} from "../../src/lib/format";

// Spelled out so a lost hard space or minus sign fails loudly.
const NBSP = " ";
const MINUS = "−";

describe("formatCop", () => {
  it("writes pesos with dots and a hard space", () => {
    expect(formatCop(380_000_000)).toBe(`$${NBSP}380.000.000`);
    expect(formatCop(1_250_000_000)).toBe(`$${NBSP}1.250.000.000`);
  });
});

describe("formatMillions", () => {
  it("writes millions", () => {
    expect(formatMillions(445_000_000)).toBe(`$${NBSP}445${NBSP}millones`);
    expect(formatMillions(1_250_000_000)).toBe(`$${NBSP}1.250${NBSP}millones`);
  });

  it("keeps one decimal at most", () => {
    expect(formatMillions(716_500_000)).toBe(`$${NBSP}716,5${NBSP}millones`);
    expect(formatMillions(389_990_000)).toBe(`$${NBSP}390${NBSP}millones`);
  });
});

describe("formatMillionsShort", () => {
  it("abbreviates millions to M, one decimal at most", () => {
    expect(formatMillionsShort(289_000_000)).toBe(`$${NBSP}289${NBSP}M`);
    expect(formatMillionsShort(427_600_000)).toBe(`$${NBSP}427,6${NBSP}M`);
    expect(formatMillionsShort(1_250_000_000)).toBe(`$${NBSP}1.250${NBSP}M`);
  });
});

describe("formatPct", () => {
  it("signs every change, with the typographic minus", () => {
    expect(formatPct(12.5)).toBe(`+12,5${NBSP}%`);
    expect(formatPct(-3)).toBe(`${MINUS}3,0${NBSP}%`);
    expect(formatPct(9.8)).toBe(`+9,8${NBSP}%`);
  });

  it("gives no sign to zero", () => {
    expect(formatPct(0)).toBe(`0,0${NBSP}%`);
  });
});

describe("formatChange", () => {
  it("says the direction in words and drops the sign", () => {
    expect(formatChange(9.8)).toBe(`Subió 9,8${NBSP}%`);
    expect(formatChange(-2.1)).toBe(`Bajó 2,1${NBSP}%`);
    expect(formatChange(0)).toBe("Sin cambio");
  });
});

describe("formatCount", () => {
  it("picks singular or plural", () => {
    expect(formatCount(1, "alcoba", "alcobas")).toBe(`1${NBSP}alcoba`);
    expect(formatCount(2, "baño", "baños")).toBe(`2${NBSP}baños`);
    expect(formatCount(0, "alcoba", "alcobas")).toBe(`0${NBSP}alcobas`);
  });
});

describe("formatArea", () => {
  it("writes square meters with a decimal comma", () => {
    expect(formatArea(58.5)).toBe(`58,5${NBSP}m²`);
    expect(formatArea(54.98)).toBe(`54,98${NBSP}m²`);
    expect(formatArea(60)).toBe(`60${NBSP}m²`);
  });
});

describe("formatDate", () => {
  it("writes day, short month and year", () => {
    expect(formatDate("2026-11-02")).toBe("2 nov 2026");
    expect(formatDate("2026-09-07")).toBe("7 sep 2026");
    expect(formatDate("2027-01-31")).toBe("31 ene 2027");
  });

  it("refuses anything but a day", () => {
    expect(() => formatDate("2026-11-02T10:00:00Z")).toThrow(/ISO date/);
    expect(() => formatDate("02/11/2026")).toThrow(/ISO date/);
  });
});

describe("formatDateShort", () => {
  it("writes dd/mm/yyyy", () => {
    expect(formatDateShort("2026-11-02")).toBe("02/11/2026");
  });
});

describe("time zones", () => {
  it("keeps the same day west of UTC", () => {
    // vitest.config.ts runs the suite in Bogotá, where midnight UTC is 7 p.m. the day before.
    expect(Intl.DateTimeFormat().resolvedOptions().timeZone).toBe("America/Bogota");
    expect(formatDate("2026-01-01")).toBe("1 ene 2026");
    expect(formatDateShort("2026-01-01")).toBe("01/01/2026");
  });
});
