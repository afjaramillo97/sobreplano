// The comparison (SPEC 11d): chosen from the search and from a project page, read from the URL,
// on one area at a time, and two columns at a time on a phone.
import AxeBuilder from "@axe-core/playwright";

import {
  expect,
  hydrated,
  PAGES,
  type Page,
  saveFinances,
  test,
  VIEWPORTS,
} from "./fixtures";

const KEY = "sobreplano.comparar.v1";

const bar = (page: Page) => page.getByRole("region", { name: "Comparador" });
const table = (page: Page) => page.getByRole("table");
const headers = (page: Page) => table(page).locator("thead th");
const units = (page: Page) => page.getByRole("row", { name: /Tipologías/ }).getByRole("cell");
const stored = (page: Page) => page.evaluate((key) => localStorage.getItem(key), KEY);

const choose = (page: Page, name: string) =>
  page.locator("#resultados").getByRole("checkbox", { name: `Comparar ${name}` }).check();

test("two from the search and one from its page compare in that order", async ({ page }) => {
  await page.goto("/proyectos/");
  await hydrated(page);
  await choose(page, "Altos de Niquía");
  await expect(bar(page)).toContainText("Comparar (1)");
  await expect(bar(page).getByRole("link", { name: "Ver comparación" })).toHaveCount(0);
  await choose(page, "Torres del Ancón");
  await expect(bar(page)).toContainText("Comparar (2)");

  await page.goto(PAGES.projectWithMap);
  await page.getByRole("button", { name: "Agregar al comparador" }).click();
  await expect(page.getByRole("button", { name: "Quitar del comparador" })).toBeVisible();
  await page.getByRole("link", { name: "Comparar (3)" }).click();
  await expect(page).toHaveURL(PAGES.compare);
  await expect(headers(page)).toHaveText([
    "Altos de Niquía",
    "Torres del Ancón",
    "Mirador de los Guaduales",
  ]);
});

test("the search holds four at most, and 'Quitar todos' empties it", async ({ page }) => {
  await page.goto("/proyectos/");
  await hydrated(page);
  const boxes = page.locator("#resultados").getByRole("checkbox");
  for (let i = 0; i < 4; i++) await boxes.nth(i).check();
  await expect(bar(page)).toContainText("Máximo 4 proyectos.");
  await expect(boxes.nth(4)).toBeDisabled();
  await bar(page).getByRole("button", { name: "Quitar todos" }).click();
  await expect(bar(page)).toHaveCount(0);
  expect(await stored(page)).toBeNull();
});

test("a missing area says 'No reportada' and stays out of the lowest price per m²", async ({
  page,
}) => {
  await page.goto(PAGES.compare);
  const mark = "Menor $/m²";
  // Private area: Altos de Niquía, the first column, does not report it.
  await expect(units(page).nth(0)).toContainText("No reportada");
  await expect(units(page).nth(1)).toContainText(mark);
  await expect(table(page).getByText(mark)).toHaveCount(1);

  await page.getByText("Área construida", { exact: true }).click();
  // Built area: now Torres del Ancón, the second, does not.
  await expect(units(page).nth(1)).toContainText("No reportada");
  await expect(units(page).nth(1)).not.toContainText("/m²");
  await expect(units(page).nth(0)).toContainText(mark);
  await expect(table(page).getByText(mark)).toHaveCount(1);
});

test("a shared link replaces the saved selection", async ({ page }) => {
  await page.goto("/proyectos/");
  await page.evaluate(
    (key) => localStorage.setItem(key, JSON.stringify({ slugs: ["altos-de-niquia"] })),
    KEY,
  );
  await page.goto("/comparar/?p=bosque-de-ditaires,terrazas-de-santa-maria");
  await expect(headers(page)).toHaveText(["Bosque de Ditaires", "Terrazas de Santa María"]);
  expect(await stored(page)).toBe(
    JSON.stringify({ slugs: ["bosque-de-ditaires", "terrazas-de-santa-maria"] }),
  );
});

test("fewer than two known projects explain how to choose", async ({ page }) => {
  await page.goto("/comparar/?p=altos-de-niquia,inexistente,altos-de-niquia");
  await expect(page.getByRole("heading", { name: "Elige al menos 2 proyectos" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Ir a la búsqueda" })).toHaveAttribute(
    "href",
    "/proyectos/",
  );
  await expect(table(page)).toHaveCount(0);
});

test("a phone shows two columns, each with its selector", async ({ page }) => {
  await page.setViewportSize(VIEWPORTS.mobile);
  await page.goto(PAGES.compare);
  await expect(headers(page)).toHaveText(["Altos de Niquía", "Torres del Ancón"]);
  const second = page.getByLabel("Columna 2");
  await second.selectOption({ label: "Mirador de los Guaduales" });
  await expect(headers(page)).toHaveText(["Altos de Niquía", "Mirador de los Guaduales"]);
  // Choosing the other column's project swaps them.
  await page.getByLabel("Columna 1").selectOption({ label: "Mirador de los Guaduales" });
  await expect(headers(page)).toHaveText(["Mirador de los Guaduales", "Altos de Niquía"]);
});

for (const [name, viewport] of Object.entries(VIEWPORTS)) {
  test(`with '¿Me alcanza?' has no axe violations at ${name}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await saveFinances(page, { incomeCop: 8_000_000, savingsCop: 90_000_000 });
    await page.goto(PAGES.compare);
    await expect(table(page)).toContainText("¿Me alcanza?");
    const { violations } = await new AxeBuilder({ page }).analyze();
    expect(violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(", ")}`)).toEqual(
      [],
    );
  });
}
