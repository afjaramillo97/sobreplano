import { describe, expect, it } from "vitest";
import type { ProjectDetailOut, ProjectOut, UnitTypeOut } from "../../src/lib/api/client";
import { MUNICIPALITY_NAMES, toProjectView, toUnitTypeView } from "../../src/lib/projects";

let ids = 0;

/** A unit type priced on `latest` (and first priced on `first`), or unpriced without them. */
function unit(
  name: string,
  prices: { latest?: [number, string]; first?: [number, string]; change?: number } = {},
  area: { private?: number; built?: number } = { private: 60 },
): UnitTypeOut {
  ids += 1;
  const { latest, first = latest, change = null } = prices;
  const basis = area.private !== undefined ? "private" : "built";
  const areaM2 = area.private ?? area.built ?? 0;
  return {
    id: `00000000-0000-0000-0000-${String(ids).padStart(12, "0")}`,
    name,
    private_area_m2: area.private ?? null,
    built_area_m2: area.built ?? null,
    bedrooms: 2,
    bathrooms: 2,
    latest_price: latest ? { price_cop: latest[0], observed_on: latest[1], source: "scraper" } : null,
    first_price: first ? { price_cop: first[0], observed_on: first[1], source: "manual" } : null,
    change_since_first_pct: change,
    price_per_m2_cop: latest ? Math.round(latest[0] / areaM2) : null,
    area_basis: basis,
  };
}

function project(unitTypes: UnitTypeOut[], extra: Partial<ProjectOut> = {}): ProjectOut {
  return {
    id: "11111111-1111-1111-1111-111111111111",
    slug: "torre-ejemplo",
    name: "Torre Ejemplo",
    developer: { name: "Constructora Ejemplo", slug: "constructora-ejemplo" },
    municipality: "envigado",
    neighborhood: "Las Vegas",
    location: { lat: 6.17, lon: -75.59 },
    source_url: "https://example.com/torre-ejemplo",
    unit_types: unitTypes,
    ...extra,
  };
}

const TODAY = "2026-11-02";
const BEFORE = "2026-10-20";

describe("unit type status", () => {
  it("is current when observed on the project's latest day", () => {
    const view = toUnitTypeView(unit("Tipo A", { latest: [400_000_000, TODAY] }), TODAY);
    expect(view.status).toBe("current");
    expect(view.priceCop).toBe(400_000_000);
    expect(view.pricePerM2Cop).toBe(6_666_667);
    expect(view.observedOn).toBe(TODAY);
  });

  it("is not-published when last seen before that day, and loses its current price", () => {
    const view = toUnitTypeView(
      unit("Tipo B", { latest: [380_000_000, BEFORE], first: [350_000_000, "2026-09-01"], change: 8.6 }),
      TODAY,
    );
    expect(view.status).toBe("not-published");
    expect(view.priceCop).toBeNull();
    expect(view.pricePerM2Cop).toBeNull();
    expect(view.observedOn).toBe(BEFORE); // "No publicada desde el 20 oct 2026"
    expect(view.changePct).toBe(8.6); // as the API gives it
    expect(view.firstPrice).toEqual({ priceCop: 350_000_000, observedOn: "2026-09-01" });
  });

  it("is no-price when it never had one", () => {
    const view = toUnitTypeView(unit("Tipo C"), TODAY);
    expect(view.status).toBe("no-price");
    expect(view.priceCop).toBeNull();
    expect(view.observedOn).toBeNull();
    expect(view.firstPrice).toBeNull();
  });
});

describe("areas", () => {
  it("prefers the private area", () => {
    const view = toUnitTypeView(unit("A", {}, { private: 58.5, built: 64 }), TODAY);
    expect(view).toMatchObject({ areaM2: 58.5, areaBasis: "private" });
  });

  it("falls back to the built area, and says so", () => {
    const view = toUnitTypeView(unit("A", { latest: [300_000_000, TODAY] }, { built: 64 }), TODAY);
    expect(view).toMatchObject({ areaM2: 64, areaBasis: "built", pricePerM2Cop: 4_687_500 });
  });

  it("refuses a unit type without any area", () => {
    expect(() => toUnitTypeView(unit("Sin área", {}, {}), TODAY)).toThrow(/has no area/);
  });
});

describe("desde", () => {
  it("is the cheapest current unit type", () => {
    const view = toProjectView(
      project([
        unit("Tipo 3", { latest: [520_000_000, TODAY], change: 4.2 }),
        unit("Tipo 1", { latest: [445_000_000, TODAY], change: 9.8 }),
        unit("Tipo 2", { latest: [480_000_000, TODAY] }),
      ]),
    );
    expect(view.lastObservedOn).toBe(TODAY);
    expect(view.from?.name).toBe("Tipo 1");
    expect(view.from?.priceCop).toBe(445_000_000);
    expect(view.from?.changePct).toBe(9.8); // the project's change is the desde's, never an average
  });

  it("ignores a cheaper unit type that stopped being published", () => {
    const view = toProjectView(
      project([
        unit("Agotada", { latest: [300_000_000, BEFORE] }),
        unit("Vigente", { latest: [410_000_000, TODAY] }),
      ]),
    );
    expect(view.from?.name).toBe("Vigente");
  });

  it("is null when nothing is current: the card says 'Sin precio publicado'", () => {
    expect(toProjectView(project([unit("Sin precio")])).from).toBeNull();
    expect(toProjectView(project([])).from).toBeNull();
    expect(toProjectView(project([])).lastObservedOn).toBeNull();
  });

  it("breaks a price tie by name", () => {
    const view = toProjectView(
      project([unit("Tipo B", { latest: [400_000_000, TODAY] }), unit("Tipo A", { latest: [400_000_000, TODAY] })]),
    );
    expect(view.from?.name).toBe("Tipo A");
  });
});

describe("unit type order", () => {
  it("puts current ones first by price, then the rest by name", () => {
    const view = toProjectView(
      project([
        unit("Tipo 10"),
        unit("Penthouse", { latest: [900_000_000, TODAY] }),
        unit("Tipo 2", { latest: [250_000_000, BEFORE] }),
        unit("Estudio", { latest: [310_000_000, TODAY] }),
        unit("Tipo 1"),
      ]),
    );
    expect(view.unitTypes.map((u) => [u.name, u.status])).toEqual([
      ["Estudio", "current"],
      ["Penthouse", "current"],
      ["Tipo 1", "no-price"],
      ["Tipo 2", "not-published"],
      ["Tipo 10", "no-price"], // numeric order: 2 before 10
    ]);
  });
});

describe("project fields", () => {
  it("copies the project, without coordinates when there are none", () => {
    const view = toProjectView(project([], { location: null, neighborhood: null }));
    expect(view).toMatchObject({
      slug: "torre-ejemplo",
      developer: { name: "Constructora Ejemplo", slug: "constructora-ejemplo" },
      municipality: "envigado",
      neighborhood: null,
      location: null,
      sourceUrl: "https://example.com/torre-ejemplo",
    });
  });

  it("never carries the price history into the view", () => {
    const withHistory = unit("Tipo A", { latest: [400_000_000, TODAY] });
    const detail: ProjectDetailOut = project([]) as ProjectDetailOut;
    detail.unit_types = [{ ...withHistory, history: [withHistory.latest_price!] }];
    const view = toProjectView(detail);
    expect(JSON.stringify(view)).not.toContain('"history"');
  });

  it("names every municipality", () => {
    expect(MUNICIPALITY_NAMES.itagui).toBe("Itagüí");
    expect(MUNICIPALITY_NAMES.la_estrella).toBe("La Estrella");
    expect(Object.keys(MUNICIPALITY_NAMES)).toHaveLength(10);
  });
});
