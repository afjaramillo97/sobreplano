import { afterEach, describe, expect, it, vi } from "vitest";

import versioned from "../../src/data/reference-rate.json";
import {
  buildReferenceRate,
  fetchReferenceRate,
  loadReferenceRate,
  oldestCutOff,
  queryUrl,
  todayInBogota,
} from "../../src/lib/reference-rate";

const TODAY = "2026-11-25";
const NO_VIS = "Adquisición de vivienda no vis (colocación en pesos)";
const VIS = "Adquisición de vivienda vis (colocación en pesos)";

// As the SODA API answered on 2026-11-25, with the week of 13 November.
const row = (product: string, weighted: string, amount: string, loans: string, cutOff = "2026-11-13") => ({
  fecha_corte: `${cutOff}T00:00:00.000`,
  producto_de_cr_dito: product,
  weighted,
  amount,
  loans,
});
const noVis = row(NO_VIS, "2619205014494.130", "169475287482.54", "737");
const vis = row(VIS, "1917376189652.6700", "131631573245.22", "1153");
const ROWS = [noVis, vis];

// The tests never reach the network: every query gets this answer.
const answering = (body: unknown, status = 200) =>
  vi.fn(async () => new Response(JSON.stringify(body), { status }));

const load = async (fetcher: () => Promise<Response>) => {
  const log = vi.fn();
  const rate = await loadReferenceRate({ live: true, fetcher, today: TODAY, log });
  return { rate, log };
};

const expectFallback = async (fetcher: () => Promise<Response>, reason: RegExp) => {
  const { rate, log } = await load(fetcher);
  expect(rate).toEqual(versioned);
  expect(log).toHaveBeenCalledOnce();
  expect(log.mock.calls[0]![0]).toMatch(reason);
  expect(log.mock.calls[0]![0]).toContain("data/reference-rate.json");
};

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("a valid answer", () => {
  it("gives the weighted rates of the latest week, with two decimals", async () => {
    const rate = await fetchReferenceRate({ fetcher: answering(ROWS), today: TODAY });
    expect(rate).toEqual({
      vis: { rateEaPct: 14.57, loans: 1153 },
      noVis: { rateEaPct: 15.45, loans: 737 },
      cutOff: "2026-11-13",
      fetchedOn: TODAY,
      source: versioned.source,
      sourceUrl: versioned.sourceUrl,
    });
  });

  it("asks for the banks' loans in pesos, grouped by week and product", async () => {
    const fetcher = answering(ROWS);
    await fetchReferenceRate({ fetcher, today: TODAY });
    expect(fetcher).toHaveBeenCalledWith(queryUrl(TODAY), expect.objectContaining({}));
    const params = new URL(queryUrl(TODAY)).searchParams;
    expect(params.get("$where")).toContain("tipo_entidad='1'");
    expect(params.get("$where")).toContain(VIS);
    expect(params.get("$where")).toContain(NO_VIS);
    expect(params.get("$where")).not.toContain("UVR");
    expect(params.get("$group")).toBe("fecha_corte,producto_de_cr_dito");
  });

  it("asks only for the weeks the validation accepts, so the API does not sum two months", () => {
    // 44 days before 25 Nov: the oldest cut-off that is still under 45 days old.
    expect(oldestCutOff(TODAY)).toBe("2026-10-12");
    expect(new URL(queryUrl(TODAY)).searchParams.get("$where")).toContain(
      "fecha_corte>='2026-10-12'",
    );
  });

  it("replaces the versioned rate without logging", async () => {
    const { rate, log } = await load(answering(ROWS));
    expect(rate.fetchedOn).toBe(TODAY);
    expect(log).not.toHaveBeenCalled();
  });
});

describe("the build falls back to the versioned file", () => {
  it("when the network is down", async () => {
    await expectFallback(() => Promise.reject(new TypeError("fetch failed")), /fetch failed/);
  });

  it("when the API answers an error", async () => {
    await expectFallback(answering({ message: "no such column" }, 400), /answered 400/);
  });

  it("when a rate is out of range", async () => {
    const high = row(NO_VIS, "31000", "1000", "737");
    await expectFallback(answering([high, vis]), /outside 5-30 %/);
    const low = row(VIS, "4990", "1000", "1153");
    await expectFallback(answering([noVis, low]), /outside 5-30 %/);
  });

  it("when a rate has too few loans behind it", async () => {
    await expectFallback(answering([noVis, { ...vis, loans: "49" }]), /only 49 loans/);
  });

  it("when the latest week is 45 days old", async () => {
    const old = ROWS.map((r) => ({ ...r, fecha_corte: "2026-10-11T00:00:00.000" }));
    await expectFallback(answering(old), /45 days old/);
  });

  it("when the latest week lacks a product", async () => {
    const stale = row(VIS, "1000", "100", "900", "2026-11-06");
    await expectFallback(answering([noVis, stale]), /no row for/);
  });

  it("when a column is renamed or empty", async () => {
    const { weighted: _, ...renamed } = vis;
    await expectFallback(answering([noVis, renamed]), /column weighted/);
    await expectFallback(answering([]), /no rows/);
    await expectFallback(answering({ error: true }), /not a list/);
  });

  it("accepts a week 44 days old", async () => {
    const rows = ROWS.map((r) => ({ ...r, fecha_corte: "2026-10-12T00:00:00.000" }));
    const rate = await fetchReferenceRate({ fetcher: answering(rows), today: TODAY });
    expect(rate.cutOff).toBe("2026-10-12");
  });
});

describe("buildReferenceRate", () => {
  it("reads the versioned file, with no query, when REFERENCE_RATE is not set", async () => {
    const network = vi.fn();
    vi.stubGlobal("fetch", network);
    vi.stubEnv("REFERENCE_RATE", "");
    expect(await buildReferenceRate()).toEqual(versioned);
    expect(network).not.toHaveBeenCalled();
  });
});

describe("the versioned file", () => {
  it("passes the same limits as the live answer", () => {
    for (const { rateEaPct, loans } of [versioned.vis, versioned.noVis]) {
      expect(rateEaPct).toBeGreaterThanOrEqual(5);
      expect(rateEaPct).toBeLessThanOrEqual(30);
      expect(loans).toBeGreaterThanOrEqual(50);
    }
    expect(versioned.cutOff).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(versioned.source).toContain("CC BY-SA 4.0");
  });
});

describe("todayInBogota", () => {
  it("is the day in Colombia, not in UTC", () => {
    expect(todayInBogota(new Date("2026-11-26T03:00:00Z"))).toBe("2026-11-25");
  });
});
