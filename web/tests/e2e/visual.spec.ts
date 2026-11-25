// Screenshots of the home page, the listing (with the map on desktops), two project pages and
// the advisor (empty, and with a conversation), on a phone and a desktop.
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
  advisor: PAGES.advisor,
} as const;

for (const [viewportName, viewport] of Object.entries(VIEWPORTS)) {
  for (const [name, path] of Object.entries(SHOTS)) {
    test(`${name} at ${viewportName}`, async ({ page }) => {
      await page.setViewportSize(viewport);
      await page.goto(path);
      await page.evaluate(() => document.fonts.ready);
      if (name.startsWith("project")) await loadHistory(page);
      // From 1024 px the listing has the map (with the local style): wait for its pills.
      if (name === "listing" && viewport.width >= 1024) {
        await expect(page.locator(".maplibregl-marker button").first()).toBeVisible();
      }
      await page.evaluate(() => window.scrollTo(0, 0));
      await expect(page).toHaveScreenshot(`${name}-${viewport.width}.png`, { fullPage: true });
    });
  }
}

// The advisor with one answer: the stream is simulated and the clock fixed, so the bubble's
// time and the list's "ahora" never change.
const ANSWER =
  'event: step\ndata: {"tool":"search_projects","phase":"start"}\n\n' +
  'event: step\ndata: {"tool":"search_projects","phase":"end"}\n\n' +
  `event: answer\ndata: ${JSON.stringify({
    thread_id: "6f1c2b9e-1d1e-4c55-9c1b-0b8a4f1d2e3f",
    reply:
      "Encontré dos proyectos en Itagüí:\n\n| Proyecto | Desde |\n| --- | --- |\n| Reserva de San Antonio | $ 289 M |\n| Bosque de Ditaires | $ 265 M |\n\n**Bosque de Ditaires** es el más barato.",
    tools_used: ["search_projects"],
    projects: ["reserva-de-san-antonio", "bosque-de-ditaires"],
    remaining_today: 27,
  })}\n\n`;

for (const [viewportName, viewport] of Object.entries(VIEWPORTS)) {
  test(`advisor-conversation at ${viewportName}`, async ({ page }) => {
    await page.clock.setFixedTime(new Date("2026-11-25T15:00:00-05:00"));
    await page.route("**/advisor/chat/stream", (route) =>
      route.fulfill({ headers: { "content-type": "text/event-stream" }, body: ANSWER }),
    );
    await page.setViewportSize(viewport);
    await page.goto(PAGES.advisor);
    await page.evaluate(() => document.fonts.ready);
    await page.getByLabel("Tu pregunta para el asesor").fill("¿Qué proyectos hay en Itagüí?");
    await page.getByLabel("Tu pregunta para el asesor").press("Enter");
    await expect(page.getByRole("log").getByRole("table")).toBeVisible();
    await page.getByLabel("Tu pregunta para el asesor").blur();
    await expect(page).toHaveScreenshot(`advisor-conversation-${viewport.width}.png`);
  });
}
