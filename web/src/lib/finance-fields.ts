/**
 * Reading and writing what a person types in the finance fields (SPEC 11d): each field gives its
 * value or the message to show beside it.
 */
import { maxPlanMonths, maxRateEaPct, minDownPaymentPct } from "./finance";

const thousands = new Intl.NumberFormat("es-CO", { useGrouping: "always" });

/**
 * Whole pesos as typed, with or without "$", dots and spaces: "$ 8.000.000" → 8000000. Null
 * for an empty field; "invalid" for anything else, a comma included (pesos take no cents).
 */
export function parseWhole(text: string): number | null | "invalid" {
  const digits = text.replace(/[$.\s]/g, "");
  if (digits === "") return text.trim() === "" ? null : "invalid";
  if (!/^\d+$/.test(digits)) return "invalid";
  const value = Number(digits);
  return Number.isSafeInteger(value) ? value : "invalid";
}

/**
 * A rate or a percentage, with a comma or a point for the decimals: "15,45" → 15.45. A separator
 * still without its decimals ("15,") reads as 15, so nothing breaks while typing.
 */
export function parseDecimal(text: string): number | null | "invalid" {
  const plain = text.trim().replace(",", ".");
  if (plain === "") return null;
  return /^\d{1,3}(\.\d*)?$/.test(plain) ? Number(plain) : "invalid";
}

/** 8000000 → "8.000.000", as a money field shows it once left. */
export function formatThousands(value: number): string {
  return thousands.format(value);
}

/** A rate or a percentage as a field shows it: 15.45 → "15,45". */
export function formatDecimalInput(value: number): string {
  return String(value).replace(".", ",");
}

/** A field's value, or why it has none. Optional fields can be empty without an error. */
export type Field = { value: number | null; error: string | null };

const ok = (value: number | null): Field => ({ value, error: null });
const failed = (error: string): Field => ({ value: null, error });
const NOT_PESOS = "Escribe solo números, en pesos.";

export function readIncome(text: string): Field {
  const value = parseWhole(text);
  if (value === null) return failed("Escribe tu ingreso mensual.");
  if (value === "invalid") return failed(NOT_PESOS);
  return value > 0 ? ok(value) : failed("El ingreso debe ser mayor que cero.");
}

export function readSavings(text: string): Field {
  const value = parseWhole(text);
  if (value === null) return failed("Escribe tu ahorro, o 0 si todavía no tienes.");
  return value === "invalid" ? failed(NOT_PESOS) : ok(value);
}

export function readMonths(text: string): Field {
  const value = parseWhole(text);
  if (value === null) return ok(null);
  return value !== "invalid" && value >= 1 && value <= maxPlanMonths
    ? ok(value)
    : failed(`Escribe un número de meses entre 1 y ${maxPlanMonths}, o déjalo vacío.`);
}

export function readRate(text: string): Field {
  const value = parseDecimal(text);
  if (value === null) return failed("Escribe una tasa o usa la de referencia.");
  return value !== "invalid" && value > 0 && value <= maxRateEaPct
    ? ok(value)
    : failed(`Escribe una tasa mayor que 0 y de máximo ${maxRateEaPct} % E.A.`);
}

export function readDownPaymentPct(text: string): Field {
  const value = parseDecimal(text);
  return typeof value === "number" && value >= minDownPaymentPct && value < 100
    ? ok(value)
    : failed(`La cuota inicial va de ${minDownPaymentPct} % a menos de 100 %.`);
}
