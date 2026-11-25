// No page scrolls sideways at 320 px, the narrowest phone width WCAG asks for (reflow).
import { expect, loadHistory, PAGES, test } from "./fixtures";

for (const [pageName, path] of Object.entries(PAGES)) {
  test(`${pageName} has no horizontal scroll at 320 px`, async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 720 });
    await page.goto(path);
    if (path.startsWith("/proyectos/") && path !== "/proyectos/") await loadHistory(page);
    const width = await page.evaluate(() => document.documentElement.scrollWidth);
    expect(width).toBeLessThanOrEqual(320);
  });
}
