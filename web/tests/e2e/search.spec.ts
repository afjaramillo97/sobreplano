// The search on /proyectos/ (SPEC 11b): filters in the URL, the map and its pills, the phone's
// map view, and the page without JavaScript. The map draws the local style (fixtures.ts).
import { expect, hydrated, MAP_HOST, type Page, test, VIEWPORTS } from "./fixtures";

// formatCount puts a hard space between the number and the noun; \s matches it.
const ZONE = /(\d+)\sproyectos? en esta zona del mapa/;

/** Waits until the map has drawn its pills, and gives the zone's count. */
async function waitForMap(page: Page): Promise<void> {
  await expect(page.locator(".maplibregl-marker button").first()).toBeVisible();
  await expect(page.getByText(ZONE)).toBeVisible();
}

async function zoneCount(page: Page): Promise<number> {
  const text = (await page.getByText(ZONE).textContent()) ?? "";
  return Number(ZONE.exec(text)?.[1]);
}

const heading = (page: Page) => page.getByRole("heading", { level: 1 });

/**
 * Three zoom steps with the keyboard, each one finished before the next: MapLibre eases a step
 * for about 300 ms, and a press during it starts from halfway, so under load the final zoom (and
 * the count read right after) would vary from run to run.
 */
async function zoomWithKeys(page: Page, key: "Minus" | "Equal"): Promise<void> {
  await page.locator(".maplibregl-canvas").focus();
  for (let i = 0; i < 3; i++) {
    await page.keyboard.press(key);
    await page.waitForTimeout(600);
  }
}
const cardNames = (page: Page) => page.locator("#resultados a h2, #resultados a h3").allTextContents();

test.describe("filters", () => {
  test("come from the URL, and each card shows the desde of the unit type that passes", async ({ page }) => {
    await page.goto("/proyectos/?municipio=itagui&alcobas=3");
    await expect(heading(page)).toHaveText("2 proyectos");
    expect((await cardNames(page)).sort()).toEqual(["Balcones del Ajizal", "Terrazas de Santa María"]);
    // Without filters Balcones del Ajizal starts at its 2-bedroom Tipo 1 (312 millones).
    const card = page.getByRole("link", { name: /Balcones del Ajizal/ });
    await expect(card).toContainText("398 millones");
    await expect(card).toContainText("Tipo 2");
    await expect(card).toContainText("3 alcobas");
  });

  test("rewrite the URL in the spec's order, and come back after a project page", async ({ page }) => {
    await page.goto("/proyectos/");
    await page.getByRole("button", { name: "Municipio" }).click();
    await page.locator("label", { hasText: "Itagüí" }).click();
    await page.getByRole("button", { name: "Alcobas" }).click();
    await page.locator("label", { hasText: "3+" }).click();
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: /Ordenar/ }).click();
    await page.locator("label", { hasText: "Mayor subida" }).click();
    await expect(page).toHaveURL("/proyectos/?municipio=itagui&alcobas=3&orden=subida");
    const names = await cardNames(page);

    await page.getByRole("link", { name: /Terrazas de Santa María/ }).click();
    await expect(page).toHaveURL("/proyectos/terrazas-de-santa-maria/");
    await page.goBack();
    await expect(page).toHaveURL("/proyectos/?municipio=itagui&alcobas=3&orden=subida");
    await expect(heading(page)).toHaveText("2 proyectos");
    expect(await cardNames(page)).toEqual(names);
  });

  test("ignore invalid values without errors, and drop them on the next write", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("console", (message) => {
      if (message.type() === "error") errors.push(message.text());
    });
    await page.goto("/proyectos/?alcobas=abc&municipio=narnia");
    await expect(heading(page)).toHaveText("14 proyectos");
    await page.getByRole("button", { name: /Ordenar/ }).click();
    await page.locator("label", { hasText: "Nombre" }).click();
    await expect(page).toHaveURL("/proyectos/?orden=nombre");
    expect(errors).toEqual([]);
  });

  test("that leave nothing say so, keep their chips, and clear in one step", async ({ page }) => {
    await page.goto("/proyectos/?q=narnia&alcobas=2");
    await expect(page.getByRole("heading", { name: "Ningún proyecto cumple estos filtros" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Quitar filtro: “narnia”" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Quitar filtro: 2+ alcobas" })).toBeVisible();
    await page.getByRole("button", { name: "Limpiar todo" }).first().click();
    await expect(heading(page)).toHaveText("14 proyectos");
    await expect(page).toHaveURL("/proyectos/");
  });

  test("open in the 'Más filtros' panel with a live count", async ({ page }) => {
    await page.goto("/proyectos/");
    await page.getByRole("button", { name: "Más filtros" }).click();
    const sheet = page.getByRole("dialog", { name: "Más filtros" });
    await expect(sheet).toBeVisible();
    await sheet.getByLabel("Constructora").selectOption("ceiba-urbana");
    await expect(sheet.getByRole("button", { name: /^Ver \d+ proyectos?$/ })).toHaveText("Ver 5 proyectos");
    await sheet.getByRole("button", { name: "Ver 5 proyectos" }).click();
    await expect(sheet).toBeHidden();
    await expect(page).toHaveURL("/proyectos/?constructora=ceiba-urbana");
  });
});

test.describe("map", () => {
  test.use({ viewport: VIEWPORTS.desktop });

  test("has a pill or a group for every result inside it, and the counter says how many", async ({ page }) => {
    await page.goto("/proyectos/");
    await waitForMap(page);
    const pills = await page.locator(".maplibregl-marker button[data-slug]").count();
    const grouped = (await page.locator(".maplibregl-marker button[data-cluster]").allTextContents())
      .map(Number)
      .reduce((a, b) => a + b, 0);
    // 13 of the 14 projects have coordinates; the fit shows them all.
    expect(pills + grouped).toBe(13);
    expect(await zoneCount(page)).toBe(13);
  });

  test("keeps projects without coordinates, apart, while it filters the list", async ({ page }) => {
    await page.goto("/proyectos/");
    await waitForMap(page);
    const apart = page.locator("section[aria-labelledby=sin-ubicacion]");
    await expect(apart.getByRole("heading", { level: 2 })).toHaveText("Sin ubicación publicada (1)");
    await expect(apart.getByRole("link", { name: /Bosque de Ditaires/ })).toBeVisible();
  });

  test("opens a floating card from a pill; Esc closes it and gives the focus back", async ({ page }) => {
    await page.goto("/proyectos/");
    await waitForMap(page);
    const pill = page.getByRole("button", { name: /^Altos de Niquía, \$\s249\sM \+4,6\s%: desde \$\s249\.000\.000, subió 4,6\s%$/ });
    await pill.click();
    await expect(pill).toHaveAttribute("data-selected", "true");
    const card = page.getByRole("dialog", { name: "Altos de Niquía" });
    await expect(card.getByRole("link", { name: /Altos de Niquía/ })).toHaveAttribute(
      "href",
      "/proyectos/altos-de-niquia/",
    );
    await page.keyboard.press("Escape");
    await expect(card).toBeHidden();
    await expect(pill).toBeFocused();
  });

  test("outlines the pill of the card under the pointer, and the other way round", async ({ page }) => {
    await page.goto("/proyectos/");
    await waitForMap(page);
    const pill = page.getByRole("button", { name: /^Altos de Niquía, \$/ });
    const card = page.locator("#resultados").getByRole("link", { name: /Altos de Niquía/ });
    await card.hover();
    await expect(pill).toHaveAttribute("data-highlighted", "true");
    await pill.hover();
    await expect(card).toHaveAttribute("data-highlighted", "true");
  });

  test("moved with the keyboard changes the counter and the list, unless told not to", async ({ page }) => {
    await page.goto("/proyectos/?mapa=6.2447,-75.5978,13.0");
    await waitForMap(page);
    const before = await zoneCount(page);
    await expect(heading(page)).toHaveText(`${before + 1} proyecto${before === 0 ? "" : "s"}`);
    await zoomWithKeys(page, "Minus");
    await expect.poll(() => zoneCount(page)).toBeGreaterThan(before);
    const after = await zoneCount(page);
    // The listed projects are those in the zone, plus the one without coordinates.
    await expect(heading(page)).toHaveText(`${after + 1} proyectos`);
    await expect(page).toHaveURL(/[?&]mapa=6\.\d{4},-75\.\d{4},\d+\.\d$/);

    await page.locator("label", { hasText: "Buscar al mover el mapa" }).click();
    await expect(page).toHaveURL(/[?&]mover=0$/);
    await expect(heading(page)).toHaveText("14 proyectos");
    await zoomWithKeys(page, "Equal");
    await expect.poll(() => zoneCount(page)).toBeLessThan(after);
    await expect(heading(page)).toHaveText("14 proyectos");
  });

  test("groups the two nearby projects and parts them on a click", async ({ page }) => {
    await page.goto("/proyectos/?mapa=6.1733,-75.6122,13.0");
    await waitForMap(page);
    const group = page.getByRole("button", { name: /^Grupo de 2 proyectos/ });
    await expect(group).toHaveText("2");
    await group.click();
    await expect(page.getByRole("button", { name: /^Balcones del Ajizal, \$/ })).toBeVisible();
    await expect(page.getByRole("button", { name: /^Terrazas de Santa María, \$/ })).toBeVisible();
  });

  test("that cannot load says so, and the list shows every result of the filters", async ({ page }) => {
    await page.route(MAP_HOST, (route) => route.fulfill({ status: 503, body: "" }));
    await page.goto("/proyectos/");
    await expect(page.getByText("No pudimos cargar el mapa. La lista sigue funcionando.")).toBeVisible();
    await expect(heading(page)).toHaveText("14 proyectos");
    await expect(page.locator("section[aria-labelledby=sin-ubicacion]")).toHaveCount(0);
  });

  test("credits OpenFreeMap, OpenMapTiles and OpenStreetMap", async ({ page }) => {
    await page.goto("/proyectos/");
    await waitForMap(page);
    await expect(page.locator(".maplibregl-ctrl-attrib")).toHaveText(
      "OpenFreeMap © OpenMapTiles Data from OpenStreetMap",
    );
  });
});

test.describe("phone", () => {
  test.use({ viewport: VIEWPORTS.mobile });

  test("shows the map on 'Ver mapa', in the URL, and goes back to the list with Atrás", async ({ page }) => {
    await page.goto("/proyectos/?municipio=medellin");
    await hydrated(page);
    await page.getByRole("button", { name: "Ver mapa" }).click();
    await expect(page).toHaveURL("/proyectos/?municipio=medellin&vista=mapa");
    await expect(page.getByText(/^\d+\sproyectos? en esta zona$/)).toBeVisible();
    await expect(page.locator(".maplibregl-ctrl-attrib")).toHaveText(
      "OpenFreeMap © OpenMapTiles Data from OpenStreetMap",
    );
    await page.goBack();
    await expect(page).toHaveURL("/proyectos/?municipio=medellin");
    await expect(page.locator(".maplibregl-map")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Ver mapa" })).toBeVisible();
  });
});

test.describe("without JavaScript", () => {
  test.use({ javaScriptEnabled: false });

  test("the listing shows the whole catalog and no controls that would not work", async ({ page }) => {
    await page.goto("/proyectos/?municipio=itagui");
    await expect(page.locator("#resultados a h2")).toHaveCount(14);
    await expect(page.getByRole("searchbox")).toBeHidden();
    await expect(page.getByRole("button", { name: "Ver mapa" })).toBeHidden();
  });

  test("the home search goes to the listing with its filters", async ({ page }) => {
    await page.goto("/");
    await page.getByLabel("Municipio").selectOption("itagui");
    await page.getByLabel("Presupuesto").selectOption("400000000");
    await page.getByRole("button", { name: "Ver proyectos", exact: true }).last().click();
    await expect(page).toHaveURL("/proyectos/?municipio=itagui&precio_max=400000000");
  });
});

test("the CSP adds only what the map needs", async ({ page }) => {
  await page.goto("/proyectos/");
  const policy = (await page.locator('meta[http-equiv="content-security-policy"]').getAttribute("content")) ?? "";
  const directive = (name: string) =>
    policy
      .split(";")
      .map((d) => d.trim())
      .find((d) => d.startsWith(`${name} `));
  expect(directive("img-src")).toBe("img-src 'self' data: blob:");
  expect(directive("worker-src")).toBe("worker-src 'self'");
  expect(directive("connect-src")).toMatch(/^connect-src 'self'( \S+)? https:\/\/tiles\.openfreemap\.org$/);
  expect(directive("default-src")).toBe("default-src 'self'");
});
