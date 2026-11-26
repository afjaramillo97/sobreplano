import { describe, expect, it } from "vitest";

import {
  formatDecimalInput,
  formatThousands,
  parseDecimal,
  parseWhole,
  readDownPaymentPct,
  readIncome,
  readMonths,
  readRate,
  readSavings,
} from "../../src/lib/finance-fields";

describe("parseWhole", () => {
  it("reads pesos with or without dots, spaces and the sign", () => {
    expect(parseWhole("8000000")).toBe(8_000_000);
    expect(parseWhole("8.000.000")).toBe(8_000_000);
    expect(parseWhole("$ 8.000.000")).toBe(8_000_000);
    expect(parseWhole("0")).toBe(0);
  });

  it("is null for an empty field", () => {
    expect(parseWhole("")).toBeNull();
    expect(parseWhole("   ")).toBeNull();
  });

  it("rejects commas, signs, words and numbers too large to be exact", () => {
    for (const text of ["8,5", "-1", "8 millones", "$", "9".repeat(20)]) {
      expect(parseWhole(text), text).toBe("invalid");
    }
  });
});

describe("parseDecimal", () => {
  it("takes a comma or a point", () => {
    expect(parseDecimal("15,45")).toBe(15.45);
    expect(parseDecimal("15.45")).toBe(15.45);
    expect(parseDecimal("30")).toBe(30);
    expect(parseDecimal("")).toBeNull();
  });

  it("reads a separator without its decimals yet, while typing", () => {
    expect(parseDecimal("15,")).toBe(15);
  });

  it("rejects anything else", () => {
    for (const text of ["15,4,5", "-3", "abc", "1e2", "1000"]) {
      expect(parseDecimal(text), text).toBe("invalid");
    }
  });
});

describe("writing numbers back", () => {
  it("groups thousands with dots, four digits included", () => {
    expect(formatThousands(8_000_000)).toBe("8.000.000");
    expect(formatThousands(5000)).toBe("5.000");
    expect(formatThousands(0)).toBe("0");
    expect(formatDecimalInput(15.45)).toBe("15,45");
  });
});

describe("the fields", () => {
  it("ask for the income and the savings, which can be zero", () => {
    expect(readIncome("8.000.000")).toEqual({ value: 8_000_000, error: null });
    expect(readIncome("").error).toMatch(/ingreso/);
    expect(readIncome("0").error).toMatch(/mayor que cero/);
    expect(readIncome("ocho").error).toMatch(/solo números/);
    expect(readSavings("0")).toEqual({ value: 0, error: null });
    expect(readSavings("").error).toMatch(/o 0/);
  });

  it("take the months only from 1 to 60, or none", () => {
    expect(readMonths("")).toEqual({ value: null, error: null });
    expect(readMonths("60").value).toBe(60);
    expect(readMonths("0").error).toMatch(/entre 1 y 60/);
    expect(readMonths("61").error).toMatch(/entre 1 y 60/);
  });

  it("hold the rate and the down payment to the ranges of the maths", () => {
    expect(readRate("40").value).toBe(40);
    for (const text of ["0", "40,01", "", "x"]) expect(readRate(text).error, text).not.toBeNull();
    expect(readDownPaymentPct("20").value).toBe(20);
    for (const text of ["19,9", "100", ""]) {
      expect(readDownPaymentPct(text).error, text).not.toBeNull();
    }
  });
});
