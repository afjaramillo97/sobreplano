/**
 * The projects chosen to compare (SPEC 11d §4): their slugs in one versioned localStorage key,
 * in the order chosen, at most MAX_COMPARED and without repeats.
 */
import { readJson, removeKey, writeJson } from "./browser-storage";

export const COMPARE_KEY = "sobreplano.comparar.v1";
export const MIN_COMPARED = 2;
export const MAX_COMPARED = 4;

export type StoredComparison = { slugs: string[] };

/** A selection as the site keeps it: no repeats, no empty values, the first MAX_COMPARED. */
export function normalizeSlugs(slugs: readonly unknown[]): string[] {
  const valid = slugs.filter((slug): slug is string => typeof slug === "string" && slug !== "");
  return [...new Set(valid)].slice(0, MAX_COMPARED);
}

/** The saved selection; empty without one or with data it cannot read. */
export function readComparison(storage: Storage | null): string[] {
  const data = readJson(storage, COMPARE_KEY) as Partial<StoredComparison> | null;
  return Array.isArray(data?.slugs) ? normalizeSlugs(data.slugs) : [];
}

/** Save the selection; false when the storage is missing or full, so the page can say so. */
export function writeComparison(storage: Storage | null, slugs: readonly string[]): boolean {
  const value: StoredComparison = { slugs: normalizeSlugs(slugs) };
  return writeJson(storage, COMPARE_KEY, value);
}

/** "Quitar todos"; false when the storage could not be reached. */
export function clearComparison(storage: Storage | null): boolean {
  return removeKey(storage, COMPARE_KEY);
}

/** The selection with slug at the end; unchanged if it is there already or the selection is full. */
export function addToComparison(slugs: readonly string[], slug: string): string[] {
  return normalizeSlugs([...slugs, slug]);
}

export function removeFromComparison(slugs: readonly string[], slug: string): string[] {
  return slugs.filter((other) => other !== slug);
}

/** Whether one more project can be chosen. */
export function isComparisonFull(slugs: readonly string[]): boolean {
  return slugs.length >= MAX_COMPARED;
}
