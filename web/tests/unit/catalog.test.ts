// The fictitious catalog (tests/fixtures/catalog.json) keeps covering the cases of SPEC 11a §6.
// seed_schema.py validates its shape; this checks that the rare cases stay in it.
import { describe, expect, it } from "vitest";
import catalog from "../fixtures/catalog.json";

type Observation = { price_cop: number; observed_at: string; source_url: string };
type Unit = {
  name: string;
  private_area_m2?: number;
  built_area_m2?: number;
  observation?: Observation;
  history?: Observation[];
};
type Project = (typeof catalog.projects)[number] & {
  neighborhood?: string;
  lat?: number;
  unit_types: Unit[];
};

const projects = catalog.projects as Project[];
const day = (o: Observation) => o.observed_at.slice(0, 10);
const prices = (u: Unit) => [...(u.history ?? []), ...(u.observation ? [u.observation] : [])];
const lastDay = (p: Project) =>
  p.unit_types.flatMap(prices).map(day).sort().at(-1) ?? null;
const units = projects.flatMap((p) => p.unit_types.map((u) => ({ p, u })));

describe("fictitious catalog", () => {
  it("has at least 12 projects, five municipalities and three developers", () => {
    expect(projects.length).toBeGreaterThanOrEqual(12);
    expect(new Set(projects.map((p) => p.municipality)).size).toBeGreaterThanOrEqual(5);
    expect(new Set(projects.map((p) => p.developer.slug)).size).toBe(3);
  });

  it("only links to example.com", () => {
    const urls = JSON.stringify(catalog).match(/https?:\/\/[^"]+/g) ?? [];
    expect(urls.length).toBeGreaterThan(0);
    for (const url of urls) expect(new URL(url).hostname).toBe("example.com");
  });

  it("has a long history: 6 changes or more over 4 months or more, with repeated days", () => {
    const long = units.find(({ u }) => {
      const list = prices(u);
      const changes = list.filter((o, i) => i > 0 && o.price_cop !== list[i - 1]!.price_cop);
      const repeats = list.length - 1 - changes.length;
      const months =
        (Date.parse(day(list.at(-1)!)) - Date.parse(day(list[0]!))) / (30 * 24 * 3600 * 1000);
      return changes.length >= 6 && repeats > 0 && months >= 4;
    });
    expect(long).toBeDefined();
  });

  it("has a price drop, a single observation and a built-area-only unit type", () => {
    expect(units.some(({ u }) => {
      const list = prices(u);
      return list.length > 1 && list.at(-1)!.price_cop < list[0]!.price_cop;
    })).toBe(true);
    expect(units.some(({ u }) => prices(u).length === 1)).toBe(true);
    expect(units.some(({ u }) => u.private_area_m2 === undefined && u.built_area_m2 !== undefined)).toBe(true);
  });

  it("has a unit type that stopped being published, cheaper than its current siblings", () => {
    const stale = units.find(({ p, u }) => u.observation && day(u.observation) < lastDay(p)!);
    expect(stale).toBeDefined();
    const current = stale!.p.unit_types.filter((u) => u.observation && day(u.observation) === lastDay(stale!.p));
    for (const u of current) expect(stale!.u.observation!.price_cop).toBeLessThan(u.observation!.price_cop);
  });

  it("has unpriced unit types, and a project with no price at all", () => {
    expect(units.some(({ p, u }) => !u.observation && p.unit_types.some((o) => o.observation))).toBe(true);
    expect(projects.some((p) => p.unit_types.every((u) => !u.observation))).toBe(true);
  });

  it("has projects with and without coordinates and neighborhood, and a long name", () => {
    expect(projects.some((p) => p.lat === undefined)).toBe(true);
    expect(projects.some((p) => p.lat !== undefined)).toBe(true);
    expect(projects.some((p) => !p.neighborhood)).toBe(true);
    expect(projects.some((p) => p.neighborhood)).toBe(true);
    expect(projects.some((p) => p.name.length >= 40)).toBe(true);
  });
});
