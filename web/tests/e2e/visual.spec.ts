// Screenshots of the home page, the listing and two project pages, on a phone and a desktop.
// They are compared only on Linux, with the official Playwright image: fonts render
// differently elsewhere (SPEC 11a, decisions). Update them with the command in docs.
import { existsSync, readdirSync } from "node:fs";
import { expect, loadHistory, PAGES, test, VIEWPORTS } from "./fixtures";

// The captures show the kit's icons; a build without the private submodule (a fork, CI
// without KIT_REPO_TOKEN) uses the fallback icons and cannot match them.
const kitIcons = existsSync("kit/icons") && readdirSync("kit/icons").some((f) => f.endsWith(".svg"));

test.skip(process.platform !== "linux", "captures are made and compared on Linux only");
test.skip(!kitIcons, "captures need the kit's icons (web/kit)");

const SHOTS = {
  home: PAGES.home,
  listing: PAGES.listing,
  "project-with-map": PAGES.projectWithMap,
  "project-without-map": PAGES.projectWithoutMap,
} as const;

for (const [viewportName, viewport] of Object.entries(VIEWPORTS)) {
  for (const [name, path] of Object.entries(SHOTS)) {
    test(`${name} at ${viewportName}`, async ({ page }) => {
      await page.setViewportSize(viewport);
      await page.goto(path);
      await page.evaluate(() => document.fonts.ready);
      if (name.startsWith("project")) await loadHistory(page);
      await page.evaluate(() => window.scrollTo(0, 0));
      await expect(page).toHaveScreenshot(`${name}-${viewport.width}.png`, { fullPage: true });
    });
  }
}
