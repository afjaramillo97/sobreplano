import { describe, expect, it } from "vitest";

import {
  addToComparison,
  clearComparison,
  COMPARE_KEY,
  compareUrl,
  isComparisonFull,
  parseCompare,
  readComparison,
  removeFromComparison,
  writeComparison,
} from "../../src/lib/compare-store";
import { MemoryStorage } from "./memory-storage";

describe("the selection", () => {
  it("keeps the order in which projects were chosen", () => {
    const slugs = ["b", "a", "c"].reduce<string[]>(addToComparison, []);
    expect(slugs).toEqual(["b", "a", "c"]);
    expect(removeFromComparison(slugs, "a")).toEqual(["b", "c"]);
  });

  it("holds no repeats", () => {
    expect(addToComparison(["a", "b"], "a")).toEqual(["a", "b"]);
  });

  it("holds four at most", () => {
    const full = ["a", "b", "c", "d"];
    expect(isComparisonFull(full)).toBe(true);
    expect(isComparisonFull(["a", "b", "c"])).toBe(false);
    expect(addToComparison(full, "e")).toEqual(full);
  });
});

describe("readComparison and writeComparison", () => {
  it("round-trips the slugs", () => {
    const storage = new MemoryStorage();
    expect(writeComparison(storage, ["torre-sur", "mirador"])).toBe(true);
    expect(readComparison(storage)).toEqual(["torre-sur", "mirador"]);
    expect(JSON.parse(storage.data.get(COMPARE_KEY)!)).toEqual({ slugs: ["torre-sur", "mirador"] });
  });

  it("is empty without the key, with broken JSON or with another shape", () => {
    const storage = new MemoryStorage();
    expect(readComparison(storage)).toEqual([]);
    for (const raw of ["{broken", '["a"]', '{"slugs":"a"}', "null"]) {
      storage.data.set(COMPARE_KEY, raw);
      expect(readComparison(storage), raw).toEqual([]);
    }
  });

  it("drops repeats, values that are not slugs and anything past the fourth", () => {
    const storage = new MemoryStorage();
    storage.data.set(COMPARE_KEY, JSON.stringify({ slugs: ["a", "a", 3, "", "b", "c", "d", "e"] }));
    expect(readComparison(storage)).toEqual(["a", "b", "c", "d"]);
  });

  it("empties with Quitar todos", () => {
    const storage = new MemoryStorage();
    writeComparison(storage, ["a"]);
    expect(clearComparison(storage)).toBe(true);
    expect(readComparison(storage)).toEqual([]);
  });

  it("says when the selection was not saved", () => {
    const storage = new MemoryStorage();
    storage.full = true;
    expect(writeComparison(storage, ["a"])).toBe(false);
    expect(writeComparison(null, ["a"])).toBe(false);
    expect(readComparison(null)).toEqual([]);
  });
});

describe("the URL of the comparison", () => {
  const known = new Set(["uno", "dos", "tres", "cuatro", "cinco"]);

  it("carries the selection in its order", () => {
    expect(compareUrl(["tres", "uno"])).toBe("/comparar/?p=tres,uno");
    expect(parseCompare("?p=tres,uno", known)).toEqual(["tres", "uno"]);
  });

  it("ignores unknown slugs and repeats", () => {
    expect(parseCompare("?p=uno,inexistente,uno", known)).toEqual(["uno"]);
    expect(parseCompare("?p=", known)).toEqual([]);
  });

  it("takes four at most", () => {
    expect(parseCompare("?p=uno,dos,tres,cuatro,cinco", known)).toEqual([
      "uno",
      "dos",
      "tres",
      "cuatro",
    ]);
  });

  it("asks for nothing without p, so the saved selection stays", () => {
    expect(parseCompare("", known)).toBeNull();
    expect(parseCompare("?otro=1", known)).toBeNull();
  });
});
