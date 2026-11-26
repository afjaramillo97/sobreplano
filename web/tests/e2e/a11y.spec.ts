// axe finds no violations on any page, on a phone and on a desktop (SPEC 11a §10), nor in the
// search's "Más filtros" panel and the phone's map view (SPEC 11b).
import AxeBuilder from "@axe-core/playwright";
import {
  expect,
  hydrated,
  PAGES,
  type Page,
  settle,
  test,
  VIEWPORTS,
} from "./fixtures";

async function expectNoViolations(page: Page) {
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(", ")}`)).toEqual([]);
}

for (const [viewportName, viewport] of Object.entries(VIEWPORTS)) {
  for (const [pageName, path] of Object.entries(PAGES)) {
    test(`${pageName} has no axe violations at ${viewportName}`, async ({ page }) => {
      await page.setViewportSize(viewport);
      await page.goto(path);
      await settle(page, path);
      // The listing's map, from 1024 px: checked once its pills are drawn.
      if ((path === PAGES.listing || path.startsWith(`${PAGES.listing}?`)) && viewport.width >= 1024) {
        await expect(page.locator(".maplibregl-marker button").first()).toBeVisible();
      }
      await expectNoViolations(page);
    });
  }

  test(`the search with "Más filtros" open has no axe violations at ${viewportName}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto(PAGES.listing);
    await hydrated(page);
    await page.getByRole("button", { name: "Más filtros" }).click();
    await expect(page.getByRole("dialog", { name: "Más filtros" }).getByLabel("Constructora")).toBeVisible();
    await expectNoViolations(page);
  });
}

test("the phone's map view has no axe violations", async ({ page }) => {
  await page.setViewportSize(VIEWPORTS.mobile);
  await page.goto(`${PAGES.listing}?vista=mapa`);
  await expect(page.locator(".maplibregl-marker button").first()).toBeVisible();
  await expectNoViolations(page);
});
