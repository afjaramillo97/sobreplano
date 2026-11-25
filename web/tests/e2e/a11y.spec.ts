// axe finds no violations on any page, on a phone and on a desktop (SPEC 11a §10).
import AxeBuilder from "@axe-core/playwright";
import { expect, isProjectPage, loadHistory, PAGES, test, VIEWPORTS } from "./fixtures";

for (const [viewportName, viewport] of Object.entries(VIEWPORTS)) {
  for (const [pageName, path] of Object.entries(PAGES)) {
    test(`${pageName} has no axe violations at ${viewportName}`, async ({ page }) => {
      await page.setViewportSize(viewport);
      await page.goto(path);
      if (isProjectPage(path)) await loadHistory(page);
      const results = await new AxeBuilder({ page }).analyze();
      expect(results.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(", ")}`)).toEqual([]);
    });
  }
}
