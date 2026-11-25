// Shared test setup: every page must load without a CSP violation in the console.
import { test as base, expect, type Page } from "@playwright/test";

export const test = base.extend<{ cspErrors: string[] }>({
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

/** The pages of the site, with one project with coordinates and one without. */
export const PAGES = {
  home: "/",
  listing: "/proyectos/",
  projectWithMap: "/proyectos/mirador-de-los-guaduales/",
  projectWithoutMap: "/proyectos/bosque-de-ditaires/",
  terms: "/terminos/",
  notFound: "/esta-pagina-no-existe/",
} as const;

export const VIEWPORTS = {
  mobile: { width: 390, height: 844 },
  desktop: { width: 1440, height: 900 },
} as const;

/** Brings the history into view, which loads the island, and waits until it settles. */
export async function loadHistory(page: Page) {
  const section = page.locator("section[aria-labelledby=historico]");
  await section.scrollIntoViewIfNeeded();
  await expect(section.locator("[aria-busy=true]")).toHaveCount(0, { timeout: 10_000 });
}
