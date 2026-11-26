import { afterEach, describe, expect, it, vi } from "vitest";

import { localStorageOrNull } from "../../src/lib/browser-storage";
import {
  clearFinances,
  EMPTY_FINANCES,
  FINANCES_KEY,
  rateEaPct,
  readFinances,
  writeFinances,
  type StoredFinances,
} from "../../src/lib/finances-store";
import { MemoryStorage } from "./memory-storage";

const NOW = new Date("2026-11-25T15:00:00Z");
const REFERENCE = {
  vis: { rateEaPct: 14.57, loans: 1153 },
  noVis: { rateEaPct: 15.45, loans: 737 },
  cutOff: "2026-11-13",
  fetchedOn: "2026-11-25",
  source: "",
  sourceUrl: "",
};

const FINANCES: StoredFinances = {
  incomeCop: 8_000_000,
  savingsCop: 60_000_000,
  housing: "vis",
  monthsToDelivery: 24,
  rate: { source: "custom", eaPct: 13.2 },
  years: 15,
  downPaymentPct: 40,
  updatedAt: NOW.toISOString(),
};

afterEach(() => vi.unstubAllGlobals());

function stored(value: unknown): MemoryStorage {
  const storage = new MemoryStorage();
  storage.data.set(FINANCES_KEY, typeof value === "string" ? value : JSON.stringify(value));
  return storage;
}

describe("defaults", () => {
  it("are not VIS, 20 years, 30 % and the reference rate", () => {
    expect(EMPTY_FINANCES).toMatchObject({
      incomeCop: null,
      savingsCop: null,
      housing: "no-vis",
      years: 20,
      downPaymentPct: 30,
      rate: { source: "reference" },
    });
  });
});

describe("readFinances and writeFinances", () => {
  it("round-trips, stamped with the time of the save", () => {
    const storage = new MemoryStorage();
    expect(writeFinances(storage, { ...FINANCES, updatedAt: "" }, NOW)).toBe(true);
    expect(readFinances(storage)).toEqual(FINANCES);
  });

  it("keeps zero savings, which is not the same as no savings", () => {
    const storage = new MemoryStorage();
    writeFinances(storage, { ...FINANCES, savingsCop: 0 }, NOW);
    expect(readFinances(storage)?.savingsCop).toBe(0);
  });

  it("is null without the key, with broken JSON or with another shape", () => {
    expect(readFinances(new MemoryStorage())).toBeNull();
    expect(readFinances(stored("{broken"))).toBeNull();
    expect(readFinances(stored([1, 2]))).toBeNull();
    expect(readFinances(stored(8_000_000))).toBeNull();
  });

  it("fills the fields another version did not write", () => {
    const old = { incomeCop: 5_000_000, savingsCop: 20_000_000 };
    expect(readFinances(stored(old))).toEqual({ ...EMPTY_FINANCES, ...old });
  });

  it("replaces a value out of range with its default", () => {
    const bad = {
      incomeCop: -1,
      savingsCop: "60000000",
      housing: "casa",
      monthsToDelivery: 61,
      rate: { source: "custom", eaPct: 41 },
      years: 4,
      downPaymentPct: 100,
      updatedAt: 5,
    };
    expect(readFinances(stored(bad))).toEqual(EMPTY_FINANCES);
    const decimals = { incomeCop: 1.5, years: 20.5, monthsToDelivery: 0, rate: "custom" };
    expect(readFinances(stored(decimals))).toEqual(EMPTY_FINANCES);
  });
});

describe("clearFinances", () => {
  it("forgets the data", () => {
    const storage = stored(FINANCES);
    expect(clearFinances(storage)).toBe(true);
    expect(readFinances(storage)).toBeNull();
    expect(storage.data.size).toBe(0);
  });
});

describe("without storage", () => {
  it("says the data was not saved, so the page keeps it in memory", () => {
    expect(readFinances(null)).toBeNull();
    expect(writeFinances(null, FINANCES, NOW)).toBe(false);
    expect(clearFinances(null)).toBe(false);
  });

  it("says so when the storage is full, and still reads and forgets", () => {
    const storage = stored(FINANCES);
    storage.full = true;
    expect(writeFinances(storage, { ...FINANCES, incomeCop: 1 }, NOW)).toBe(false);
    expect(readFinances(storage)).toEqual(FINANCES);
    expect(clearFinances(storage)).toBe(true);
  });

  it("is null when the browser refuses access to localStorage", () => {
    vi.stubGlobal("window", {
      get localStorage(): Storage {
        throw new DOMException("blocked", "SecurityError");
      },
    });
    expect(localStorageOrNull()).toBeNull();
  });
});

describe("rateEaPct", () => {
  it("follows the reference rate of the chosen kind of housing", () => {
    expect(rateEaPct(EMPTY_FINANCES, REFERENCE)).toBe(15.45);
    expect(rateEaPct({ ...EMPTY_FINANCES, housing: "vis" }, REFERENCE)).toBe(14.57);
  });

  it("is the person's own once they change it", () => {
    expect(rateEaPct(FINANCES, REFERENCE)).toBe(13.2);
  });
});
