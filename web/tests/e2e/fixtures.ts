// Shared test setup: every page must load without a CSP violation in the console, and the map
// never reaches the network: OpenFreeMap's style is answered with a local one (SPEC 11b).
import { readFileSync } from "node:fs";
import { test as base, expect, type Page } from "@playwright/test";

/** A style with land only: no tiles, fonts or sprites, so the map draws without the network. */
export const MAP_STYLE = readFileSync(new URL("../fixtures/map-style.json", import.meta.url), "utf8");
export const MAP_HOST = "https://tiles.openfreemap.org/**";

export const test = base.extend<{ cspErrors: string[]; offlineMap: void }>({
  offlineMap: [
    async ({ page }, use) => {
      await page.route(MAP_HOST, (route) =>
        route.request().url().includes("/styles/")
          ? route.fulfill({ contentType: "application/json", body: MAP_STYLE })
          : route.abort(),
      );
      await use();
    },
    { auto: true },
  ],
  cspErrors: [
    async ({ page }, use) => {
      const errors: string[] = [];
      page.on("console", (message) => {
        if (message.text().includes("Content Security Policy")) errors.push(message.text());
      });
      await use(errors);
      expect(errors, "CSP violations in the console").toEqual([]);
    },
    { auto: true },
  ],
});

export { expect };
export type { Page };

/** The pages of the site, with one project with coordinates and one without. */
export const PAGES = {
  home: "/",
  listing: "/proyectos/",
  listingFiltered: "/proyectos/?municipio=itagui&alcobas=3",
  projectWithMap: "/proyectos/mirador-de-los-guaduales/",
  projectWithoutMap: "/proyectos/bosque-de-ditaires/",
  terms: "/terminos/",
  advisor: "/asesor/",
  calculator: "/calculadora/",
  // Three projects: one without private area, one without built area, one with both.
  compare: "/comparar/?p=altos-de-niquia,torres-del-ancon,mirador-de-los-guaduales",
  notFound: "/esta-pagina-no-existe/",
} as const;

export const VIEWPORTS = {
  mobile: { width: 390, height: 844 },
  desktop: { width: 1440, height: 900 },
} as const;

/** Whether a path is a project page, whose history island loads on view. */
export const isProjectPage = (path: string) => /^\/proyectos\/[a-z0-9-]+\/$/.test(path);

/**
 * Waits until every island on screen has hydrated. A button of the server render clicked before
 * that does nothing, and typed text would be lost. Islands that load on view (client:visible)
 * count until they are scrolled to.
 */
export async function hydrated(page: Page) {
  await expect(page.locator("astro-island[ssr]")).toHaveCount(0);
}

/**
 * Leaves finances saved before the first page loads, once: a reload keeps what the test or the
 * page did with them.
 */
export async function saveFinances(
  page: Page,
  finances: { incomeCop: number; savingsCop: number; monthsToDelivery?: number },
) {
  await page.addInitScript((value) => {
    if (sessionStorage.getItem("finances-seeded")) return;
    localStorage.setItem("sobreplano.finanzas.v1", value);
    sessionStorage.setItem("finances-seeded", "1");
  }, JSON.stringify(finances));
}

/** Waits for what a page draws only in the browser, before looking at it. */
export async function settle(page: Page, path: string) {
  if (isProjectPage(path)) await loadHistory(page);
  if (path.startsWith("/comparar/")) await expect(page.getByRole("table")).toBeVisible();
}

/** Brings the history into view, which loads the island, and waits until it settles. */
export async function loadHistory(page: Page) {
  const section = page.locator("section[aria-labelledby=historico]");
  await section.scrollIntoViewIfNeeded();
  await expect(section.locator("[aria-busy=true]")).toHaveCount(0, { timeout: 10_000 });
}
