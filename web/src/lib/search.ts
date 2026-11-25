/**
 * Search over the catalog in the browser (SPEC 11b): the index the build hands to the island,
 * the search state and its URL, and the rules for matching, the "desde" and the order.
 *
 * Everything here is pure, so the island only renders, and tests/unit/search.test.ts pins
 * every rule. No API call: the catalog is small, and the API's list limit (30 a minute per IP)
 * would run out while the map moves.
 */
import type { Municipality } from "./api/client";
import { formatChange, formatCop, formatMillionsShort, formatPct } from "./format";
import { MUNICIPALITY_NAMES, type ProjectView } from "./projects";

export type SearchUnit = {
  name: string;
  bedrooms: number | null;
  bathrooms: number | null;
  areaM2: number;
  areaBasis: "private" | "built";
  priceCop: number;
  changePct: number | null;
};

export type SearchItem = {
  slug: string;
  name: string;
  developer: { name: string; slug: string };
  municipality: Municipality;
  neighborhood: string | null;
  location: { lat: number; lon: number } | null;
  /** The day of every current price: a unit type is current only on its project's last day. */
  lastObservedOn: string | null;
  /** Current unit types only, cheapest first. */
  units: SearchUnit[];
  /** Name, neighborhood, municipality and developer, lower case and without accents. */
  searchText: string;
};

export const SORTS = ["precio", "precio_desc", "subida", "nombre"] as const;
export type SortKey = (typeof SORTS)[number];

export type MapView = { lat: number; lon: number; zoom: number };

export type SearchState = {
  q: string;
  municipalities: Municipality[];
  developer: string | null;
  /** Pesos. */
  priceMin: number | null;
  priceMax: number | null;
  bedroomsMin: number | null;
  bathroomsMin: number | null;
  /** Square meters. */
  areaMin: number | null;
  areaMax: number | null;
  sort: SortKey;
  map: MapView | null;
  searchOnMove: boolean;
  /** Only counts below 1024 px, where the list and the map take turns. */
  view: "lista" | "mapa";
};

export const DEFAULT_SEARCH: SearchState = {
  q: "",
  municipalities: [],
  developer: null,
  priceMin: null,
  priceMax: null,
  bedroomsMin: null,
  bathroomsMin: null,
  areaMin: null,
  areaMax: null,
  sort: "precio",
  map: null,
  searchOnMove: true,
  view: "lista",
};

/** Every municipality, in the API's order; the URL lists them in this order. */
export const MUNICIPALITIES = Object.keys(MUNICIPALITY_NAMES) as Municipality[];

export const Q_MAX_LENGTH = 80;
/** Bounds of the bedroom and bathroom minimums. */
export const ROOMS_MIN = 1;
export const ROOMS_MAX = 5;
const PRICE_LIMIT = 1_000_000_000_000;
const AREA_LIMIT = 100_000;
const MILLION = 1_000_000;

/** Lower case, without accents and with single spaces: "Itagüí  " → "itagui". */
export function normalizeText(text: string): string {
  return text.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase().replace(/\s+/g, " ").trim();
}

const collator = new Intl.Collator("es-CO", { numeric: true, sensitivity: "base" });

/**
 * The search entry of a project. Copies only what the cards already show: never the history,
 * which stays out of the static site (SPEC 11a).
 */
export function toSearchItem(project: ProjectView): SearchItem {
  const units: SearchUnit[] = [];
  for (const unit of project.unitTypes) {
    if (unit.status !== "current" || unit.priceCop === null) continue;
    units.push({
      name: unit.name,
      bedrooms: unit.bedrooms,
      bathrooms: unit.bathrooms,
      areaM2: unit.areaM2,
      areaBasis: unit.areaBasis,
      priceCop: unit.priceCop,
      changePct: unit.changePct,
    });
  }
  units.sort((a, b) => a.priceCop - b.priceCop || collator.compare(a.name, b.name));
  return {
    slug: project.slug,
    name: project.name,
    developer: { name: project.developer.name, slug: project.developer.slug },
    municipality: project.municipality,
    neighborhood: project.neighborhood,
    location: project.location ? { lat: project.location.lat, lon: project.location.lon } : null,
    lastObservedOn: project.lastObservedOn,
    units,
    searchText: normalizeText(
      [
        project.name,
        project.neighborhood ?? "",
        MUNICIPALITY_NAMES[project.municipality],
        project.developer.name,
      ].join(" "),
    ),
  };
}

// --- The URL --------------------------------------------------------------------------------

/** A whole number written with digits only, within [min, max]; null otherwise. */
function parseInteger(value: string | null, min: number, max: number): number | null {
  if (value === null || !/^\d{1,13}$/.test(value)) return null;
  const n = Number(value);
  return n >= min && n <= max ? n : null;
}

/** A range whose minimum is above its maximum is dropped whole: there is no way to read it. */
function parseRange(
  minValue: string | null,
  maxValue: string | null,
  limit: number,
): [number | null, number | null] {
  const min = parseInteger(minValue, 0, limit);
  const max = parseInteger(maxValue, 0, limit);
  return min !== null && max !== null && min > max ? [null, null] : [min, max];
}

const round = (value: number, decimals: number) => Number(value.toFixed(decimals));

function parseMap(value: string | null): MapView | null {
  const match = value?.match(/^(-?\d{1,2}(?:\.\d+)?),(-?\d{1,3}(?:\.\d+)?),(\d{1,2}(?:\.\d+)?)$/);
  if (!match) return null;
  const [lat, lon, zoom] = match.slice(1).map(Number) as [number, number, number];
  // Web Mercator stops at about ±85°; MapLibre's zoom goes from 0 to 22.
  if (Math.abs(lat) > 85 || Math.abs(lon) > 180 || zoom > 22) return null;
  return { lat: round(lat, 4), lon: round(lon, 4), zoom: round(zoom, 1) };
}

const SLUG = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

/**
 * The search a URL asks for. Never throws: an invalid or unknown value is ignored, so it drops
 * out of the URL on the next write.
 *
 * `developers` are the slugs the catalog knows; without them any well-formed slug is kept.
 */
export function parseSearch(
  params: URLSearchParams,
  known: { developers?: readonly string[] } = {},
): SearchState {
  const q = (params.get("q") ?? "").replace(/\s+/g, " ").trim().slice(0, Q_MAX_LENGTH).trim();
  const asked = new Set((params.get("municipio") ?? "").split(","));
  const municipalities = MUNICIPALITIES.filter((m) => asked.has(m));
  const developerValue = params.get("constructora");
  const developer =
    developerValue !== null &&
    SLUG.test(developerValue) &&
    (known.developers === undefined || known.developers.includes(developerValue))
      ? developerValue
      : null;
  const [priceMin, priceMax] = parseRange(
    params.get("precio_min"),
    params.get("precio_max"),
    PRICE_LIMIT,
  );
  const [areaMin, areaMax] = parseRange(params.get("area_min"), params.get("area_max"), AREA_LIMIT);
  const sortValue = params.get("orden");
  const sort = SORTS.find((s) => s === sortValue) ?? DEFAULT_SEARCH.sort;
  return {
    q,
    municipalities,
    developer,
    priceMin,
    priceMax,
    bedroomsMin: parseInteger(params.get("alcobas"), ROOMS_MIN, ROOMS_MAX),
    bathroomsMin: parseInteger(params.get("banos"), ROOMS_MIN, ROOMS_MAX),
    areaMin,
    areaMax,
    sort,
    map: parseMap(params.get("mapa")),
    searchOnMove: params.get("mover") !== "0",
    view: params.get("vista") === "mapa" ? "mapa" : "lista",
  };
}

/**
 * The query string of a search, without "?": parameters in the order of SPEC 11b §2 and
 * default values left out, so one search always gives one URL. Commas stay readable.
 */
export function serializeSearch(state: SearchState): string {
  const parts: string[] = [];
  const add = (key: string, value: string | number) => parts.push(`${key}=${value}`);
  const q = state.q.replace(/\s+/g, " ").trim().slice(0, Q_MAX_LENGTH).trim();
  if (q) add("q", encodeURIComponent(q).replace(/%20/g, "+"));
  const municipalities = MUNICIPALITIES.filter((m) => state.municipalities.includes(m));
  if (municipalities.length > 0) add("municipio", municipalities.join(","));
  if (state.developer) add("constructora", encodeURIComponent(state.developer));
  if (state.priceMin !== null) add("precio_min", state.priceMin);
  if (state.priceMax !== null) add("precio_max", state.priceMax);
  if (state.bedroomsMin !== null) add("alcobas", state.bedroomsMin);
  if (state.bathroomsMin !== null) add("banos", state.bathroomsMin);
  if (state.areaMin !== null) add("area_min", state.areaMin);
  if (state.areaMax !== null) add("area_max", state.areaMax);
  if (state.sort !== DEFAULT_SEARCH.sort) add("orden", state.sort);
  if (state.map) {
    const { lat, lon, zoom } = state.map;
    add("mapa", `${lat.toFixed(4)},${lon.toFixed(4)},${zoom.toFixed(1)}`);
  }
  if (!state.searchOnMove) add("mover", 0);
  if (state.view === "mapa") add("vista", "mapa");
  return parts.join("&");
}

// --- Matching and order ---------------------------------------------------------------------

/** Whether the search filters by unit type: price, bedrooms, bathrooms or area. */
export function hasUnitFilters(state: SearchState): boolean {
  return (
    state.priceMin !== null ||
    state.priceMax !== null ||
    state.bedroomsMin !== null ||
    state.bathroomsMin !== null ||
    state.areaMin !== null ||
    state.areaMax !== null
  );
}

/** All the unit filters, on this one unit type. A missing bedroom count never passes a minimum. */
function unitMatches(unit: SearchUnit, state: SearchState): boolean {
  const atLeast = (value: number | null, min: number | null) =>
    min === null || (value !== null && value >= min);
  return (
    (state.priceMin === null || unit.priceCop >= state.priceMin) &&
    (state.priceMax === null || unit.priceCop <= state.priceMax) &&
    atLeast(unit.bedrooms, state.bedroomsMin) &&
    atLeast(unit.bathrooms, state.bathroomsMin) &&
    (state.areaMin === null || unit.areaM2 >= state.areaMin) &&
    (state.areaMax === null || unit.areaM2 <= state.areaMax)
  );
}

function matchesProject(item: SearchItem, state: SearchState): boolean {
  const words = normalizeText(state.q).split(" ").filter(Boolean);
  return (
    words.every((word) => item.searchText.includes(word)) &&
    (state.municipalities.length === 0 || state.municipalities.includes(item.municipality)) &&
    (state.developer === null || item.developer.slug === state.developer)
  );
}

/**
 * The unit types of a project that pass the search, cheapest first, or null if the project
 * does not pass. Without unit filters every project passes, priced or not, with all its
 * current unit types (possibly none).
 */
export function matchProject(item: SearchItem, state: SearchState): SearchUnit[] | null {
  if (!matchesProject(item, state)) return null;
  if (!hasUnitFilters(state)) return item.units;
  const units = item.units.filter((unit) => unitMatches(unit, state));
  return units.length > 0 ? units : null;
}

export type SearchResult = {
  item: SearchItem;
  /** The cheapest unit type that passes the search: the "desde" its card and pill show. */
  from: SearchUnit | null;
};

/** Missing values go last, whatever the direction. */
function nullsLast(a: number | null | undefined, b: number | null | undefined): number | null {
  const aMissing = a === null || a === undefined;
  const bMissing = b === null || b === undefined;
  if (aMissing && bMissing) return 0;
  if (aMissing) return 1;
  if (bMissing) return -1;
  return null;
}

const byName = (a: SearchResult, b: SearchResult) =>
  collator.compare(a.item.name, b.item.name) || (a.item.slug < b.item.slug ? -1 : 1);

function compareBy(
  value: (r: SearchResult) => number | null | undefined,
  direction: 1 | -1,
): (a: SearchResult, b: SearchResult) => number {
  return (a, b) => {
    const va = value(a);
    const vb = value(b);
    const missing = nullsLast(va, vb);
    if (missing !== null) return missing || byName(a, b);
    return direction * ((va as number) - (vb as number)) || byName(a, b);
  };
}

const COMPARE: Record<SortKey, (a: SearchResult, b: SearchResult) => number> = {
  precio: compareBy((r) => r.from?.priceCop, 1),
  precio_desc: compareBy((r) => r.from?.priceCop, -1),
  subida: compareBy((r) => r.from?.changePct, -1),
  nombre: byName,
};

/** The projects that pass the search, each with its "desde", in the search's order. */
export function searchResults(items: readonly SearchItem[], state: SearchState): SearchResult[] {
  const results: SearchResult[] = [];
  for (const item of items) {
    const units = matchProject(item, state);
    if (units !== null) results.push({ item, from: units[0] ?? null });
  }
  return results.sort(COMPARE[state.sort]);
}

// --- The map --------------------------------------------------------------------------------

export type Bounds = { west: number; south: number; east: number; north: number };

/** Whether a location falls inside the bounds; a project without coordinates never does. */
export function inBounds(location: SearchItem["location"], bounds: Bounds): boolean {
  if (location === null) return false;
  return (
    location.lat >= bounds.south &&
    location.lat <= bounds.north &&
    location.lon >= bounds.west &&
    location.lon <= bounds.east
  );
}

/**
 * The results the map filter keeps: those inside the bounds, and apart those without
 * coordinates, which never disappear (they go to "Sin ubicación publicada").
 */
export function splitByBounds(
  results: readonly SearchResult[],
  bounds: Bounds,
): { inside: SearchResult[]; unlocated: SearchResult[] } {
  const inside: SearchResult[] = [];
  const unlocated: SearchResult[] = [];
  for (const result of results) {
    if (result.item.location === null) unlocated.push(result);
    else if (inBounds(result.item.location, bounds)) inside.push(result);
  }
  return { inside, unlocated };
}

/** The pill's text: "$ 289 M +9,8 %", or "Sin precio". */
export function pillText(from: SearchUnit | null): string {
  if (from === null) return "Sin precio";
  const price = formatMillionsShort(from.priceCop);
  return from.changePct === null ? price : `${price} ${formatPct(from.changePct)}`;
}

/** The pill's accessible name: "Torre, desde $ 289.000.000, subió 9,8 %". */
export function pillLabel(item: SearchItem, from: SearchUnit | null): string {
  if (from === null) return `${item.name}, sin precio publicado`;
  const price = `${item.name}, desde ${formatCop(from.priceCop)}`;
  return from.changePct === null ? price : `${price}, ${formatChange(from.changePct).toLowerCase()}`;
}

// --- Filters panel --------------------------------------------------------------------------

export type PriceHistogram = { min: number; max: number; bins: number[] };

/** The cheapest and dearest current price of the catalog, to the million; null without prices. */
export function priceRange(items: readonly SearchItem[]): { min: number; max: number } | null {
  let low = Number.POSITIVE_INFINITY;
  let high = Number.NEGATIVE_INFINITY;
  for (const item of items) {
    for (const unit of item.units) {
      low = Math.min(low, unit.priceCop);
      high = Math.max(high, unit.priceCop);
    }
  }
  if (low === Number.POSITIVE_INFINITY) return null;
  const min = Math.floor(low / MILLION) * MILLION;
  const max = Math.max(Math.ceil(high / MILLION) * MILLION, min + MILLION);
  return { min, max };
}

/** The smallest and largest current unit type of the catalog, in whole m²; null without any. */
export function areaRange(items: readonly SearchItem[]): { min: number; max: number } | null {
  const areas = items.flatMap((item) => item.units.map((unit) => unit.areaM2));
  if (areas.length === 0) return null;
  const min = Math.floor(Math.min(...areas));
  return { min, max: Math.max(Math.ceil(Math.max(...areas)), min + 1) };
}

/**
 * The price filter's histogram: how many projects that pass the other filters have their
 * "desde" in each of `binCount` equal slices of the catalog's price range. Null without prices.
 */
export function priceHistogram(
  items: readonly SearchItem[],
  state: SearchState,
  binCount = 24,
): PriceHistogram | null {
  const range = priceRange(items);
  if (range === null) return null;
  const bins = Array.from({ length: binCount }, () => 0);
  const width = (range.max - range.min) / binCount;
  const others = { ...state, priceMin: null, priceMax: null };
  for (const { from } of searchResults(items, others)) {
    if (from === null) continue;
    const index = Math.min(binCount - 1, Math.floor((from.priceCop - range.min) / width));
    bins[index] = (bins[index] ?? 0) + 1;
  }
  return { ...range, bins };
}

/** The filters set, as the number on the "Más filtros" button. Order and map do not count. */
export function activeFilterCount(state: SearchState): number {
  return activeChips(state, new Map()).length;
}

export type FilterChip = {
  /** Stable key for React and tests. */
  id: string;
  label: string;
  /** The search without this filter. */
  without: SearchState;
};

function rangeLabel(min: number | null, max: number | null, format: (n: number) => string) {
  if (min !== null && max !== null) return `${format(min)} a ${format(max)}`;
  if (min !== null) return `${format(min)} o más`;
  return `hasta ${format(max as number)}`;
}

/**
 * One chip per active filter, each with the search it leaves when removed. `developers` maps
 * slugs to names; an unknown slug shows as is.
 */
export function activeChips(
  state: SearchState,
  developers: ReadonlyMap<string, string>,
): FilterChip[] {
  const chips: FilterChip[] = [];
  const q = state.q.trim();
  if (q) chips.push({ id: "q", label: `“${q}”`, without: { ...state, q: "" } });
  for (const m of state.municipalities) {
    chips.push({
      id: `municipio-${m}`,
      label: MUNICIPALITY_NAMES[m],
      without: { ...state, municipalities: state.municipalities.filter((x) => x !== m) },
    });
  }
  if (state.developer) {
    chips.push({
      id: "constructora",
      label: developers.get(state.developer) ?? state.developer,
      without: { ...state, developer: null },
    });
  }
  if (state.priceMin !== null || state.priceMax !== null) {
    chips.push({
      id: "precio",
      label: `Precio: ${rangeLabel(state.priceMin, state.priceMax, formatMillionsShort)}`,
      without: { ...state, priceMin: null, priceMax: null },
    });
  }
  if (state.bedroomsMin !== null) {
    chips.push({
      id: "alcobas",
      label: `${state.bedroomsMin}+ alcobas`,
      without: { ...state, bedroomsMin: null },
    });
  }
  if (state.bathroomsMin !== null) {
    chips.push({
      id: "banos",
      label: `${state.bathroomsMin}+ baños`,
      without: { ...state, bathroomsMin: null },
    });
  }
  if (state.areaMin !== null || state.areaMax !== null) {
    chips.push({
      id: "area",
      label: `Área: ${rangeLabel(state.areaMin, state.areaMax, (n) => `${n} m²`)}`,
      without: { ...state, areaMin: null, areaMax: null },
    });
  }
  return chips;
}

/** The search without any filter; the order, the map and the view stay. */
export function clearFilters(state: SearchState): SearchState {
  return {
    ...state,
    q: "",
    municipalities: [],
    developer: null,
    priceMin: null,
    priceMax: null,
    bedroomsMin: null,
    bathroomsMin: null,
    areaMin: null,
    areaMax: null,
  };
}

/** The developers of the catalog, by name. */
export function developerOptions(items: readonly SearchItem[]): { slug: string; name: string }[] {
  const bySlug = new Map(items.map((item) => [item.developer.slug, item.developer.name]));
  return [...bySlug]
    .map(([slug, name]) => ({ slug, name }))
    .sort((a, b) => collator.compare(a.name, b.name));
}

/** The municipalities that have projects, by name. */
export function municipalityOptions(items: readonly { municipality: Municipality }[]): Municipality[] {
  return [...new Set(items.map((item) => item.municipality))].sort((a, b) =>
    collator.compare(MUNICIPALITY_NAMES[a], MUNICIPALITY_NAMES[b]),
  );
}
