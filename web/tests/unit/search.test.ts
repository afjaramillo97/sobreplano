import { describe, expect, it } from "vitest";
import type { ProjectView, UnitTypeView } from "../../src/lib/projects";
import {
  activeChips,
  activeFilterCount,
  areaRange,
  clearFilters,
  DEFAULT_SEARCH,
  developerOptions,
  inBounds,
  matchProject,
  municipalityOptions,
  normalizeText,
  parseSearch,
  pillLabel,
  pillText,
  priceHistogram,
  priceRange,
  type SearchItem,
  type SearchState,
  type SearchUnit,
  searchResults,
  serializeSearch,
  splitByBounds,
  toSearchItem,
} from "../../src/lib/search";

const NBSP = "\u00a0";

function unit(name: string, priceCop: number, extra: Partial<SearchUnit> = {}): SearchUnit {
  return {
    name,
    bedrooms: 2,
    bathrooms: 2,
    areaM2: 60,
    areaBasis: "private",
    priceCop,
    changePct: null,
    ...extra,
  };
}

function item(name: string, units: SearchUnit[], extra: Partial<SearchItem> = {}): SearchItem {
  const base = {
    slug: normalizeText(name).replace(/ /g, "-"),
    name,
    developer: { name: "Constructora Ejemplo", slug: "constructora-ejemplo" },
    municipality: "medellin" as const,
    neighborhood: null,
    location: { lat: 6.2, lon: -75.6 },
    lastObservedOn: units.length > 0 ? "2026-11-02" : null,
    units: [...units].sort((a, b) => a.priceCop - b.priceCop),
    ...extra,
  };
  return { ...base, searchText: normalizeText(`${base.name} ${base.neighborhood ?? ""} ${base.developer.name}`) };
}

const search = (query: string) => parseSearch(new URLSearchParams(query));
const names = (state: SearchState, items: SearchItem[]) =>
  searchResults(items, state).map((r) => r.item.name);

describe("normalizeText", () => {
  it("drops accents, case and extra spaces", () => {
    expect(normalizeText("  Itagüí   Zúñiga ")).toBe("itagui zuniga");
    expect(normalizeText("MEDELLÍN")).toBe("medellin");
  });
});

describe("toSearchItem", () => {
  const current = (name: string, priceCop: number, extra: Partial<UnitTypeView> = {}): UnitTypeView => ({
    id: name,
    name,
    bedrooms: 2,
    bathrooms: 1,
    areaM2: 50,
    areaBasis: "private",
    privateAreaM2: 50,
    builtAreaM2: null,
    priceCop,
    pricePerM2Cop: 1,
    observedOn: "2026-11-02",
    firstPrice: { priceCop, observedOn: "2026-07-01" },
    changePct: 4.2,
    status: "current",
    ...extra,
  });
  const project: ProjectView = {
    slug: "torre-sur",
    name: "Torre Sur",
    developer: { name: "Ceiba Urbana", slug: "ceiba-urbana" },
    municipality: "itagui",
    neighborhood: "San Antonio de Prado",
    location: null,
    sourceUrl: "https://example.com",
    lastObservedOn: "2026-11-02",
    from: null,
    unitTypes: [
      current("Tipo B", 400),
      current("Tipo A", 300),
      current("Viejo", 100, { status: "not-published", priceCop: null, observedOn: "2026-10-01" }),
      current("Sin precio", 0, { status: "no-price", priceCop: null, observedOn: null }),
    ],
  };

  it("keeps only current unit types, cheapest first", () => {
    const entry = toSearchItem(project);
    expect(entry.units.map((u) => u.name)).toEqual(["Tipo A", "Tipo B"]);
    expect(entry.units[0]).toEqual({
      name: "Tipo A",
      bedrooms: 2,
      bathrooms: 1,
      areaM2: 50,
      areaBasis: "private",
      priceCop: 300,
      changePct: 4.2,
    });
  });

  it("indexes name, neighborhood, municipality and developer without accents", () => {
    expect(toSearchItem(project).searchText).toBe("torre sur san antonio de prado itagui ceiba urbana");
  });

  it("copies no history and no source URL", () => {
    const json = JSON.stringify(toSearchItem(project));
    expect(json).not.toContain("firstPrice");
    expect(json).not.toContain("history");
    expect(json).not.toContain("example.com");
  });
});

describe("parseSearch and serializeSearch", () => {
  const full: SearchState = {
    q: "ditaires",
    municipalities: ["itagui", "envigado"],
    developer: "constructora-ejemplo",
    priceMin: 200_000_000,
    priceMax: 400_000_000,
    bedroomsMin: 2,
    bathroomsMin: 1,
    areaMin: 50,
    areaMax: 90,
    sort: "subida",
    map: { lat: 6.1725, lon: -75.613, zoom: 12.5 },
    searchOnMove: false,
    view: "mapa",
  };

  it("writes every parameter in the order of the spec", () => {
    expect(serializeSearch(full)).toBe(
      "q=ditaires&municipio=itagui,envigado&constructora=constructora-ejemplo" +
        "&precio_min=200000000&precio_max=400000000&alcobas=2&banos=1&area_min=50&area_max=90" +
        "&orden=subida&mapa=6.1725,-75.6130,12.5&mover=0&vista=mapa",
    );
  });

  it("reads back what it writes", () => {
    expect(parseSearch(new URLSearchParams(serializeSearch(full)))).toEqual(full);
  });

  it("leaves default values out", () => {
    expect(serializeSearch(DEFAULT_SEARCH)).toBe("");
    expect(search("")).toEqual(DEFAULT_SEARCH);
  });

  it("gives one URL per search, whatever the order the municipalities came in", () => {
    const a = serializeSearch(search("municipio=envigado,itagui"));
    const b = serializeSearch(search("municipio=itagui,envigado"));
    expect(a).toBe(b);
    expect(a).toBe("municipio=itagui,envigado");
  });

  it("encodes free text, spaces as +", () => {
    const url = serializeSearch({ ...DEFAULT_SEARCH, q: "  Belén  Rosales&co " });
    expect(url).toBe("q=Bel%C3%A9n+Rosales%26co");
    expect(parseSearch(new URLSearchParams(url)).q).toBe("Belén Rosales&co");
  });

  it("cuts free text at 80 characters", () => {
    expect(search(`q=${"a".repeat(120)}`).q).toHaveLength(80);
  });

  it("reads the home page form, with empty fields", () => {
    expect(search("municipio=&precio_max=")).toEqual(DEFAULT_SEARCH);
    expect(search("municipio=bello&precio_max=300000000")).toMatchObject({
      municipalities: ["bello"],
      priceMax: 300_000_000,
    });
  });

  it("ignores invalid and unknown values, never throwing", () => {
    expect(search("alcobas=abc&municipio=narnia")).toEqual(DEFAULT_SEARCH);
    expect(
      search(
        "alcobas=0&banos=6&precio_min=-1&precio_max=1e9&area_min=50.5&orden=barato" +
          "&mapa=91,0,10&mover=no&vista=satelite&constructora=Bad Slug",
      ),
    ).toEqual(DEFAULT_SEARCH);
    expect(search("mapa=6.2,-75.6,23").map).toBeNull();
    expect(search("mapa=6.2;-75.6;12").map).toBeNull();
  });

  it("keeps the known municipalities of a list and drops the rest", () => {
    expect(search("municipio=narnia,bello,bello").municipalities).toEqual(["bello"]);
  });

  it("drops a range whose minimum is above its maximum", () => {
    const state = search("precio_min=500000000&precio_max=300000000&area_min=90&area_max=50");
    expect([state.priceMin, state.priceMax, state.areaMin, state.areaMax]).toEqual([null, null, null, null]);
  });

  it("checks the developer against the catalog when it knows it", () => {
    const params = new URLSearchParams("constructora=otra");
    expect(parseSearch(params).developer).toBe("otra");
    expect(parseSearch(params, { developers: ["ceiba-urbana"] }).developer).toBeNull();
  });

  it("rounds the map to 4 decimals and the zoom to 1", () => {
    expect(search("mapa=6.123456,-75.987654,11.26").map).toEqual({ lat: 6.1235, lon: -75.9877, zoom: 11.3 });
  });

  it("drops invalid values on the next write", () => {
    const url = serializeSearch({ ...search("alcobas=abc&municipio=narnia&banos=2"), sort: "nombre" });
    expect(url).toBe("banos=2&orden=nombre");
  });
});

describe("matchProject", () => {
  const torre = item("Torre", [
    unit("Tipo 1", 250_000_000, { bedrooms: 2, bathrooms: 1, areaM2: 50 }),
    unit("Tipo 2", 450_000_000, { bedrooms: 3, bathrooms: 2, areaM2: 80 }),
  ]);

  it("passes every project without unit filters, priced or not", () => {
    expect(matchProject(torre, DEFAULT_SEARCH)).toHaveLength(2);
    expect(matchProject(item("Sin precio", []), DEFAULT_SEARCH)).toEqual([]);
  });

  it("asks all unit filters of one unit type, never a mix", () => {
    // 3 bedrooms exist (Tipo 2) and under 300 M exists (Tipo 1), but not in the same one.
    const state = { ...DEFAULT_SEARCH, bedroomsMin: 3, priceMax: 300_000_000 };
    expect(matchProject(torre, state)).toBeNull();
    expect(matchProject(torre, { ...state, priceMax: 450_000_000 })?.map((u) => u.name)).toEqual(["Tipo 2"]);
  });

  it("applies each unit filter", () => {
    const pass = (patch: Partial<SearchState>) =>
      matchProject(torre, { ...DEFAULT_SEARCH, ...patch })?.map((u) => u.name) ?? null;
    expect(pass({ priceMin: 300_000_000 })).toEqual(["Tipo 2"]);
    expect(pass({ priceMax: 250_000_000 })).toEqual(["Tipo 1"]);
    expect(pass({ bathroomsMin: 2 })).toEqual(["Tipo 2"]);
    expect(pass({ areaMin: 60 })).toEqual(["Tipo 2"]);
    expect(pass({ areaMax: 60 })).toEqual(["Tipo 1"]);
    expect(pass({ bedroomsMin: 4 })).toBeNull();
  });

  it("leaves out a project without prices once a unit filter is set", () => {
    expect(matchProject(item("Sin precio", []), { ...DEFAULT_SEARCH, bedroomsMin: 1 })).toBeNull();
  });

  it("never passes a minimum with an unknown bedroom count", () => {
    const studio = item("Estudio", [unit("Loft", 200, { bedrooms: null })]);
    expect(matchProject(studio, { ...DEFAULT_SEARCH, bedroomsMin: 1 })).toBeNull();
  });

  it("filters by municipality and developer", () => {
    expect(matchProject(torre, { ...DEFAULT_SEARCH, municipalities: ["bello", "medellin"] })).not.toBeNull();
    expect(matchProject(torre, { ...DEFAULT_SEARCH, municipalities: ["bello"] })).toBeNull();
    expect(matchProject(torre, { ...DEFAULT_SEARCH, developer: "constructora-ejemplo" })).not.toBeNull();
    expect(matchProject(torre, { ...DEFAULT_SEARCH, developer: "otra" })).toBeNull();
  });

  it("finds text without accents or case, every word anywhere", () => {
    const belen = item("Arboleda de Belén", [], { neighborhood: "Belén Rosales" });
    const fixed = { ...belen, searchText: normalizeText("Arboleda de Belén Belén Rosales Medellín Piedra Azul") };
    for (const q of ["belen", "BELÉN", "arboleda rosales", "piedra", "medellin"]) {
      expect(matchProject(fixed, { ...DEFAULT_SEARCH, q }), q).not.toBeNull();
    }
    expect(matchProject(fixed, { ...DEFAULT_SEARCH, q: "belen poblado" })).toBeNull();
  });
});

describe("searchResults", () => {
  const items = [
    item("Bravo", [unit("B1", 300, { changePct: 2 }), unit("B2", 500, { bedrooms: 3, changePct: 9 })]),
    item("Alfa", [unit("A1", 300, { changePct: 5 })]),
    item("Delta", []),
    item("Charlie", [unit("C1", 100)]),
    item("Eco", [unit("E1", 700, { changePct: 5 })]),
  ];

  it("sorts by price, cheapest first, ties by name, unpriced last", () => {
    expect(names(DEFAULT_SEARCH, items)).toEqual(["Charlie", "Alfa", "Bravo", "Eco", "Delta"]);
  });

  it("sorts by price, dearest first, unpriced still last", () => {
    expect(names({ ...DEFAULT_SEARCH, sort: "precio_desc" }, items)).toEqual([
      "Eco",
      "Alfa",
      "Bravo",
      "Charlie",
      "Delta",
    ]);
  });

  it("sorts by rise, biggest first, ties by name, no change last", () => {
    expect(names({ ...DEFAULT_SEARCH, sort: "subida" }, items)).toEqual([
      "Alfa",
      "Eco",
      "Bravo",
      "Charlie",
      "Delta",
    ]);
  });

  it("sorts by name with natural numbers", () => {
    const numbered = [item("Torre 10", []), item("Torre 2", []), item("Árbol", [])];
    expect(names({ ...DEFAULT_SEARCH, sort: "nombre" }, numbered)).toEqual(["Árbol", "Torre 2", "Torre 10"]);
  });

  it("takes the desde from the unit types that pass, for the card and the order", () => {
    const state = { ...DEFAULT_SEARCH, bedroomsMin: 3, sort: "subida" as const };
    const results = searchResults(items, state);
    expect(results.map((r) => [r.item.name, r.from?.name])).toEqual([["Bravo", "B2"]]);
    // Without filters, Bravo's desde is B1 and its rise is 2 %.
    expect(searchResults(items, DEFAULT_SEARCH).find((r) => r.item.name === "Bravo")?.from?.name).toBe("B1");
  });
});

describe("map bounds", () => {
  const bounds = { west: -75.7, south: 6.1, east: -75.5, north: 6.3 };

  it("keeps locations inside, edges included", () => {
    expect(inBounds({ lat: 6.2, lon: -75.6 }, bounds)).toBe(true);
    expect(inBounds({ lat: 6.3, lon: -75.5 }, bounds)).toBe(true);
    expect(inBounds({ lat: 6.4, lon: -75.6 }, bounds)).toBe(false);
    expect(inBounds(null, bounds)).toBe(false);
  });

  it("never loses a project without coordinates", () => {
    const results = searchResults(
      [
        item("Dentro", [unit("A", 1)]),
        item("Fuera", [unit("A", 2)], { location: { lat: 6.34, lon: -75.54 } }),
        item("Sin mapa", [unit("A", 3)], { location: null }),
      ],
      DEFAULT_SEARCH,
    );
    const { inside, unlocated } = splitByBounds(results, bounds);
    expect(inside.map((r) => r.item.name)).toEqual(["Dentro"]);
    expect(unlocated.map((r) => r.item.name)).toEqual(["Sin mapa"]);
  });
});

describe("pills", () => {
  const torre = item("Torre", []);

  it("shows the desde in millions and its change", () => {
    expect(pillText(unit("A", 289_000_000, { changePct: 9.8 }))).toBe(`$${NBSP}289${NBSP}M +9,8${NBSP}%`);
    expect(pillText(unit("A", 289_000_000))).toBe(`$${NBSP}289${NBSP}M`);
    expect(pillText(null)).toBe("Sin precio");
  });

  it("names the pill with its visible text, the price in pesos and the change in words", () => {
    expect(pillLabel(torre, unit("A", 289_000_000, { changePct: 9.8 }))).toBe(
      `Torre, $${NBSP}289${NBSP}M +9,8${NBSP}%: desde $${NBSP}289.000.000, subió 9,8${NBSP}%`,
    );
    expect(pillLabel(torre, unit("A", 289_000_000, { changePct: -2 }))).toBe(
      `Torre, $${NBSP}289${NBSP}M \u22122,0${NBSP}%: desde $${NBSP}289.000.000, bajó 2,0${NBSP}%`,
    );
    expect(pillLabel(torre, unit("A", 289_000_000))).toBe(`Torre, $${NBSP}289${NBSP}M: desde $${NBSP}289.000.000`);
    expect(pillLabel(torre, null)).toBe("Torre, sin precio publicado");
  });
});

describe("priceHistogram", () => {
  const items = [
    item("A", [unit("A1", 240_500_000), unit("A2", 300_000_000, { bedrooms: 3 })]),
    item("B", [unit("B1", 480_000_000, { bedrooms: 3 })]),
    item("C", [unit("C1", 719_200_000)], { municipality: "bello" }),
    item("D", []),
  ];

  it("spans the catalog's prices, rounded to the million", () => {
    expect(priceRange(items)).toEqual({ min: 240_000_000, max: 720_000_000 });
    expect(priceRange([item("D", [])])).toBeNull();
  });

  it("spans the catalog's areas in whole m²", () => {
    const sized = [item("A", [unit("A1", 1, { areaM2: 38.4 }), unit("A2", 2, { areaM2: 118.2 })])];
    expect(areaRange(sized)).toEqual({ min: 38, max: 119 });
    expect(areaRange([item("D", [])])).toBeNull();
  });

  it("counts the desde of the projects that pass the other filters", () => {
    const all = priceHistogram(items, DEFAULT_SEARCH);
    expect(all?.bins).toHaveLength(24);
    expect(all?.bins.reduce((a, b) => a + b)).toBe(3);
    // 20 M per bar: A at 240,5 M in the first, B at 480 M in the 13th, C in the last.
    expect(all?.bins[0]).toBe(1);
    expect(all?.bins[12]).toBe(1);
    expect(all?.bins[23]).toBe(1);
  });

  it("ignores the price filter itself and follows the rest", () => {
    const state = { ...DEFAULT_SEARCH, bedroomsMin: 3, priceMax: 250_000_000, municipalities: ["medellin" as const] };
    const bins = priceHistogram(items, state)?.bins ?? [];
    // A's desde with 3 bedrooms is A2 at 300 M (bar 3); B stays at 480 M; C is in Bello.
    expect(bins[3]).toBe(1);
    expect(bins[12]).toBe(1);
    expect(bins.reduce((a, b) => a + b)).toBe(2);
  });
});

describe("chips", () => {
  const state: SearchState = {
    ...DEFAULT_SEARCH,
    q: "laureles",
    municipalities: ["medellin", "envigado"],
    developer: "ceiba-urbana",
    priceMax: 400_000_000,
    bedroomsMin: 2,
    bathroomsMin: 2,
    areaMin: 50,
    areaMax: 80,
    sort: "nombre",
  };
  const developers = new Map([["ceiba-urbana", "Ceiba Urbana"]]);

  it("shows one chip per filter, with readable labels", () => {
    expect(activeChips(state, developers).map((c) => c.label)).toEqual([
      "“laureles”",
      "Medellín",
      "Envigado",
      "Ceiba Urbana",
      `Precio: hasta $${NBSP}400${NBSP}M`,
      "2+ alcobas",
      "2+ baños",
      "Área: 50 m² a 80 m²",
    ]);
    expect(activeFilterCount(state)).toBe(8);
  });

  it("removes only its own filter", () => {
    const chip = activeChips(state, developers).find((c) => c.id === "municipio-medellin");
    expect(chip?.without.municipalities).toEqual(["envigado"]);
    expect(chip?.without.q).toBe("laureles");
  });

  it("labels open ranges", () => {
    const labels = activeChips({ ...DEFAULT_SEARCH, priceMin: 250_000_000, areaMax: 70 }, new Map()).map((c) => c.label);
    expect(labels).toEqual([`Precio: $${NBSP}250${NBSP}M o más`, "Área: hasta 70 m²"]);
  });

  it("clears every filter but keeps order, map and view", () => {
    const map = { lat: 6.2, lon: -75.6, zoom: 12 };
    const cleared = clearFilters({ ...state, map, view: "mapa", searchOnMove: false });
    expect(cleared).toEqual({ ...DEFAULT_SEARCH, sort: "nombre", map, view: "mapa", searchOnMove: false });
    expect(activeChips(cleared, developers)).toEqual([]);
  });
});

describe("options", () => {
  const items = [
    item("A", [], { municipality: "medellin", developer: { name: "Zeta", slug: "zeta" } }),
    item("B", [], { municipality: "itagui", developer: { name: "Alfa", slug: "alfa" } }),
    item("C", [], { municipality: "bello", developer: { name: "Zeta", slug: "zeta" } }),
  ];

  it("lists developers and municipalities once, by name", () => {
    expect(developerOptions(items)).toEqual([
      { slug: "alfa", name: "Alfa" },
      { slug: "zeta", name: "Zeta" },
    ]);
    expect(municipalityOptions(items)).toEqual(["bello", "itagui", "medellin"]);
  });
});
