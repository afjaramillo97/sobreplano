// The project page: honest prices, the history island's states, and the keyboard.
import { expect, loadHistory, PAGES, test } from "./fixtures";

const DETAIL = /\/projects\/mirador-de-los-guaduales$/;
const CORS = {
  "access-control-allow-origin": `http://localhost:${process.env.E2E_PORT ?? 4321}`,
  "access-control-expose-headers": "Retry-After",
};

test("a project without a current price says so, on the card and on its page", async ({ page }) => {
  await page.goto(PAGES.listing);
  const card = page.getByRole("link", { name: /Reserva de San Antonio/ });
  await expect(card).toContainText("Sin precio publicado");
  await page.goto("/proyectos/reserva-de-san-antonio/");
  await expect(page.getByRole("heading", { level: 2, name: "Sin precio publicado" })).toBeVisible();
});

test("a unit type that stopped being published shows since when and is not the desde", async ({
  page,
}) => {
  await page.goto("/proyectos/distrito-laureles/");
  const priceCard = page.locator("section[aria-labelledby=precio-titulo]");
  // Estudio (341 millones) stopped being published; Tipo 2 (536 millones) is the desde.
  await expect(priceCard).toContainText("536");
  await expect(priceCard).toContainText("Tipo 2");
  await expect(priceCard).not.toContainText("Estudio");
  const row = page.getByRole("row", { name: /Estudio/ });
  await expect(row).toContainText("No publicada desde el 3 oct 2026");
});

test("a 429 shows when the chart comes back, keeps the price, and is not retried", async ({ page }) => {
  const requests: string[] = [];
  page.on("request", (request) => {
    if (DETAIL.test(request.url()) && request.method() === "GET") requests.push(request.url());
  });
  await page.route(DETAIL, (route) =>
    route.fulfill({
      status: 429,
      headers: { ...CORS, "Retry-After": "120", "content-type": "application/json" },
      body: JSON.stringify({ detail: "too many requests" }),
    }),
  );
  await page.goto(PAGES.projectWithMap);
  await loadHistory(page);
  // The page has other live regions ("¿Me alcanza?", the comparison button).
  await expect(page.locator("section[aria-labelledby=historico]").getByRole("status")).toContainText(
    /Consultaste muchas fichas en poco tiempo\. Podrás ver la gráfica a las \d{1,2}:\d{2}/,
  );
  await expect(page.locator("section[aria-labelledby=precio-titulo]")).toBeVisible();
  await expect(page.getByRole("region", { name: /Tipologías de/ })).toBeVisible();
  await page.waitForTimeout(2_500); // longer than TanStack Query's first retry delay
  expect(requests).toHaveLength(1);
});

test("a server error offers to retry, and retrying asks again", async ({ page }) => {
  let calls = 0;
  await page.route(DETAIL, (route) => {
    calls += 1;
    return route.fulfill({ status: 500, headers: CORS, body: "{}" });
  });
  await page.goto(PAGES.projectWithMap);
  await loadHistory(page);
  const retry = page.getByRole("button", { name: "Reintentar" });
  await expect(retry).toBeVisible({ timeout: 10_000 });
  const before = calls; // the first request and its single automatic retry
  expect(before).toBe(2);
  await retry.click();
  await expect.poll(() => calls).toBeGreaterThan(before);
});

test("the unit type tabs work with the keyboard alone, with a visible focus", async ({ page }) => {
  await page.goto(PAGES.projectWithMap);
  await loadHistory(page);
  const selected = page.getByRole("tab", { selected: true });
  await expect(selected).toHaveText("Tipo A");

  // Tab from the top of the page until the selected tab has the focus.
  await page.locator("body").focus();
  for (let i = 0; i < 60; i += 1) {
    await page.keyboard.press("Tab");
    if (await selected.evaluate((el) => el === document.activeElement)) break;
    const focused = await page.evaluate(() => {
      const el = document.activeElement as HTMLElement | null;
      if (!el || el === document.body) return { outline: "none", what: "body" };
      return { outline: getComputedStyle(el).outlineStyle, what: el.outerHTML.slice(0, 120) };
    });
    expect(focused.outline, `focus is visible on ${focused.what}`).not.toBe("none");
  }
  await expect(selected).toBeFocused();

  await page.keyboard.press("ArrowRight");
  const next = page.getByRole("tab", { name: "Tipo B" });
  await expect(next).toBeFocused();
  await expect(next).toHaveAttribute("aria-selected", "true");
  const outline = await next.evaluate((el) => getComputedStyle(el).outlineStyle);
  expect(outline).not.toBe("none");
});
