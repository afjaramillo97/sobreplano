import { afterEach, describe, expect, it, vi } from "vitest";
import { createApiClient, type ProjectOut } from "../../src/lib/api/client";
import { catalogStats, fetchAllProjects, mostRisen, sortByFrom } from "../../src/lib/catalog";
import type { ProjectView, UnitTypeView } from "../../src/lib/projects";

afterEach(() => vi.unstubAllGlobals());

function view(name: string, price: number | null, change: number | null = null, first = "2026-07-01", last = "2026-11-02"): ProjectView {
  const unit: UnitTypeView = {
    id: name,
    name: "Tipo A",
    bedrooms: 2,
    bathrooms: 2,
    areaM2: 60,
    areaBasis: "private",
    privateAreaM2: 60,
    builtAreaM2: null,
    priceCop: price,
    pricePerM2Cop: null,
    observedOn: price === null ? null : last,
    firstPrice: price === null ? null : { priceCop: price, observedOn: first },
    changePct: change,
    status: price === null ? "no-price" : "current",
  };
  return {
    slug: name.toLowerCase().replace(/\s+/g, "-"),
    name,
    developer: { name: "Dev", slug: "dev" },
    municipality: "medellin",
    neighborhood: null,
    location: null,
    sourceUrl: "https://example.com",
    lastObservedOn: price === null ? null : last,
    from: price === null ? null : unit,
    unitTypes: [unit],
  };
}

describe("sortByFrom", () => {
  it("puts the cheapest first and projects without a price last, by name", () => {
    const sorted = sortByFrom([view("Zeta", null), view("Beta", 500), view("Alfa", null), view("Gama", 300)]);
    expect(sorted.map((p) => p.name)).toEqual(["Gama", "Beta", "Alfa", "Zeta"]);
  });
});

describe("mostRisen", () => {
  it("keeps only rises, biggest first, at most three", () => {
    const top = mostRisen([
      view("A", 1, 4.3),
      view("B", 1, -2.1),
      view("C", 1, 17.1),
      view("D", 1, null),
      view("E", 1, 9.8),
      view("F", 1, 6),
      view("G", 1, 0),
    ]);
    expect(top.map((p) => p.name)).toEqual(["C", "E", "F"]);
  });

  it("is empty when nothing rose, so the home page drops the section", () => {
    expect(mostRisen([view("A", 1, -1), view("B", null)])).toEqual([]);
  });
});

describe("catalogStats", () => {
  it("counts projects, days of history (both ends) and the last review", () => {
    const stats = catalogStats([
      view("A", 1, 1, "2026-07-01", "2026-11-02"),
      view("B", 1, 1, "2026-09-07", "2026-11-01"),
      view("C", null),
    ]);
    expect(stats).toEqual({ projects: 3, historyDays: 125, lastObservedOn: "2026-11-02" });
  });

  it("has no history without prices", () => {
    expect(catalogStats([view("A", null)])).toEqual({ projects: 1, historyDays: 0, lastObservedOn: null });
  });
});

describe("fetchAllProjects", () => {
  const project = (i: number) => ({ slug: `p-${i}` }) as ProjectOut;

  it("walks the pages 50 at a time until the total", async () => {
    const offsets: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (request: Request) => {
        const url = new URL(request.url);
        const offset = Number(url.searchParams.get("offset"));
        offsets.push(`${url.searchParams.get("limit")}@${offset}`);
        const items = Array.from({ length: Math.min(50, 120 - offset) }, (_, i) => project(offset + i));
        return Response.json({ items, total: 120, limit: 50, offset });
      }),
    );
    const projects = await fetchAllProjects(createApiClient("http://api.test"));
    expect(projects).toHaveLength(120);
    expect(offsets).toEqual(["50@0", "50@50", "50@100"]);
  });

  it("fails the build when the API fails", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Response.json({ detail: "down" }, { status: 503 })));
    await expect(fetchAllProjects(createApiClient("http://api.test"))).rejects.toThrow(/503/);
  });
});
