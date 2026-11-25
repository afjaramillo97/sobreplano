/**
 * The catalog as the build sees it: every project from GET /projects, as view models, plus
 * the few figures the home page shows. Nothing here is invented: every number comes from the
 * data (DESIGN.md, rule 5).
 */
import { type ApiClient, buildApiClient, type ProjectOut } from "./api/client";
import { type ProjectView, toProjectView } from "./projects";

// The API's largest page; the offset is capped at 1000 (SPEC 10), so 1050 projects at most.
const PAGE_SIZE = 50;
const MAX_OFFSET = 1000;

/**
 * Every project, walking GET /projects 50 at a time until `total`.
 *
 * Throws on any API error, or if the catalog outgrows what the API lets a client page through:
 * a build with missing projects must fail, not publish a partial site.
 */
export async function fetchAllProjects(api: ApiClient): Promise<ProjectOut[]> {
  const projects: ProjectOut[] = [];
  for (let offset = 0; ; offset += PAGE_SIZE) {
    if (offset > MAX_OFFSET) {
      throw new Error(`the catalog has more than ${MAX_OFFSET + PAGE_SIZE} projects`);
    }
    const { data, error, response } = await api.GET("/projects", {
      params: { query: { limit: PAGE_SIZE, offset } },
    });
    if (!data) {
      throw new Error(`GET /projects?offset=${offset} failed (${response.status}): ${JSON.stringify(error)}`);
    }
    projects.push(...data.items);
    if (projects.length >= data.total || data.items.length === 0) return projects;
  }
}

let cached: Promise<ProjectView[]> | undefined;

/** The whole catalog as view models, fetched once per build and shared by every page. */
export function loadCatalog(): Promise<ProjectView[]> {
  cached ??= fetchAllProjects(buildApiClient()).then((items) => items.map(toProjectView));
  return cached;
}

/** For the listing: cheapest "desde" first; projects without a current price last, by name. */
export function sortByFrom(projects: ProjectView[]): ProjectView[] {
  return [...projects].sort((a, b) => {
    const pa = a.from?.priceCop ?? null;
    const pb = b.from?.priceCop ?? null;
    if (pa !== null && pb !== null && pa !== pb) return pa - pb;
    if ((pa === null) !== (pb === null)) return pa === null ? 1 : -1;
    return a.name.localeCompare(b.name, "es-CO", { numeric: true, sensitivity: "base" });
  });
}

/** Up to `n` projects whose "desde" rose since its first price, biggest rise first. */
export function mostRisen(projects: ProjectView[], n = 3): ProjectView[] {
  return projects
    .filter((p) => (p.from?.changePct ?? 0) > 0)
    .sort((a, b) => (b.from?.changePct ?? 0) - (a.from?.changePct ?? 0) || a.name.localeCompare(b.name, "es-CO"))
    .slice(0, n);
}

const DAY_MS = 24 * 60 * 60 * 1000;

export type CatalogStats = {
  projects: number;
  /** Days from the first observed price to the latest one, both counted. 0 without prices. */
  historyDays: number;
  /** The latest observation in the whole catalog: the date of the last review. */
  lastObservedOn: string | null;
};

/** The real figures of the home page. */
export function catalogStats(projects: ProjectView[]): CatalogStats {
  const firsts: string[] = [];
  const lasts: string[] = [];
  for (const project of projects) {
    if (project.lastObservedOn) lasts.push(project.lastObservedOn);
    for (const unit of project.unitTypes) {
      if (unit.firstPrice) firsts.push(unit.firstPrice.observedOn);
    }
  }
  // ISO days compare as text.
  const first = firsts.sort()[0];
  const last = lasts.sort().at(-1);
  const historyDays =
    first && last ? Math.round((Date.parse(last) - Date.parse(first)) / DAY_MS) + 1 : 0;
  return { projects: projects.length, historyDays, lastObservedOn: last ?? null };
}
