// The calculator and "¿Me alcanza?" (SPEC 11d): the figures of Python, the data that stays in
// this browser and never travels, and the three answers of a project page. Nothing here reaches
// the network: the build reads the versioned reference rate.
import { readFileSync } from "node:fs";
import AxeBuilder from "@axe-core/playwright";

import { maxAffordablePrice, simulateMortgage } from "../../src/lib/finance";
import { formatCop } from "../../src/lib/format";
import { expect, hydrated, type Page, saveFinances, test, VIEWPORTS } from "./fixtures";

const CALCULATOR = "/calculadora/";
const KEY = "sobreplano.finanzas.v1";
const INCOME = "Ingreso mensual del hogar";
const SAVINGS = "Ahorro para la cuota inicial";

const json = (name: string) => JSON.parse(readFileSync(new URL(name, import.meta.url), "utf8"));
const vectors = json("../fixtures/finance-vectors.json");
const reference = json("../../src/data/reference-rate.json");

// The acceptance case of SPEC 11d. Python's answer comes from the vectors; after `rate:update`
// moves the reference rate away from theirs, from the port they hold equal to Python.
const CASE = {
  monthlyIncomeCop: 8_000_000,
  savingsCop: 60_000_000,
  rateEaPct: String(reference.noVis.rateEaPct),
  years: 20,
  downPaymentPct: "30",
};
const same = (a: object, b: object) => JSON.stringify(a) === JSON.stringify(b);
const expected =
  vectors.affordability.find((c: { input: object }) => same(c.input, CASE))?.output ??
  maxAffordablePrice(CASE);
const loanInput = { priceCop: expected.maxPriceCop, rateEaPct: CASE.rateEaPct, years: 20, downPaymentPct: "30" };
const loan =
  vectors.mortgage.find((c: { input: object }) => same(c.input, loanInput))?.output ??
  simulateMortgage(loanInput);

const result = (page: Page) => page.getByRole("status");
const block = (page: Page) => page.getByRole("region", { name: "¿Me alcanza?" });

async function openCalculator(page: Page) {
  await page.goto(CALCULATOR);
  await hydrated(page);
}

async function fill(page: Page, income: string, savings: string) {
  await page.getByLabel(INCOME).fill(income);
  await page.getByLabel(SAVINGS).fill(savings);
  await page.getByLabel(SAVINGS).blur();
}

async function expectNoViolations(page: Page) {
  const { violations } = await new AxeBuilder({ page }).analyze();
  expect(violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(", ")}`)).toEqual([]);
}

test.describe("calculator", () => {
  test("gives Python's max price, payment and limit at the reference rate", async ({ page }) => {
    await openCalculator(page);
    await fill(page, "8000000", "60000000");
    await expect(page.getByLabel(INCOME)).toHaveValue("8.000.000");
    await expect(result(page)).toContainText(formatCop(expected.maxPriceCop));
    await expect(result(page)).toContainText(formatCop(loan.monthlyPaymentCop));
    await expect(result(page)).toContainText(
      expected.limitedBy === "savings" ? "Lo limita tu ahorro" : "Lo limita tu ingreso",
    );
    // The source, the license and the week of the rate are in view (SPEC 11d).
    await expect(page.getByRole("link", { name: /Superfinanciera/ })).toHaveAttribute(
      "href",
      reference.sourceUrl,
    );
    await expect(page.getByText("licencia CC BY-SA 4.0")).toBeVisible();
    await expect(page.getByText(/semana del \d+ \w+ \d{4}/)).toBeVisible();
  });

  test("links to the search up to the max price, which shows those projects", async ({ page }) => {
    await openCalculator(page);
    await fill(page, "8000000", "150000000");
    const link = page.getByRole("link", { name: /^Ver \d+ proyectos hasta/ });
    await expect(link).toHaveText(/^Ver 4\sproyectos hasta/);
    const href = await link.getAttribute("href");
    expect(href).toMatch(/^\/proyectos\/\?precio_max=\d+$/);
    await link.click();
    await expect(page).toHaveURL(href!);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("4 proyectos");
  });

  test("shows the three cheapest, with what is missing, when none fits", async ({ page }) => {
    await openCalculator(page);
    await fill(page, "8000000", "20000000");
    await expect(page.getByText("Ningún proyecto del catálogo llega a ese precio.")).toBeVisible();
    await expect(page.getByText(/^Te faltarían/)).toHaveCount(3);
    await expect(page.getByRole("link", { name: "Terrazas de Santa María" })).toBeVisible();
    await expect(page.getByRole("link", { name: /^Ver \d+ proyectos? hasta/ })).toHaveCount(0);
  });

  test("keeps the data after a reload, until 'Olvidar mis datos'", async ({ page }) => {
    await openCalculator(page);
    await fill(page, "8000000", "150000000");
    await page.getByLabel("Meses hasta la entrega (opcional)").fill("24");
    await page.reload();
    await expect(page.getByLabel(INCOME)).toHaveValue("8.000.000");
    await expect(page.getByLabel(SAVINGS)).toHaveValue("150.000.000");
    await expect(page.getByLabel("Meses hasta la entrega (opcional)")).toHaveValue("24");

    await page.getByRole("button", { name: "Olvidar mis datos" }).click();
    await expect(page.getByLabel(INCOME)).toHaveValue("");
    await expect(page.getByLabel(SAVINGS)).toHaveValue("");
    await expect(result(page)).toContainText("Escribe tu ingreso mensual y tu ahorro");
    expect(await page.evaluate((key) => localStorage.getItem(key), KEY)).toBeNull();
  });

  test("uses a custom rate until 'Usar la tasa de referencia'", async ({ page }) => {
    await openCalculator(page);
    await fill(page, "8000000", "150000000");
    const atReference = await result(page).innerText();
    await page.getByText("Ajustes del crédito").click();
    const rate = page.getByLabel("Tasa de interés (efectiva anual)");
    await rate.fill("12,5");
    await expect(page.getByText(/Estás usando tu tasa: 12,50/)).toBeVisible();
    await expect(result(page)).toContainText("12,50");
    await page.reload();
    await expect(page.getByText(/Estás usando tu tasa: 12,50/)).toBeVisible();

    await page.getByRole("button", { name: "Usar la tasa de referencia" }).click();
    await expect(page.getByText(/Estás usando tu tasa/)).toHaveCount(0);
    await expect(result(page)).toHaveText(atReference, { useInnerText: true });
  });

  test("shows an error beside the field that is wrong, and no result", async ({ page }) => {
    await openCalculator(page);
    await fill(page, "8000000", "150000000");
    await page.getByText("Ajustes del crédito").click();
    const downPayment = page.getByLabel("Cuota inicial", { exact: true });
    await downPayment.fill("10");
    await downPayment.blur();
    await expect(downPayment).toHaveAttribute("aria-invalid", "true");
    await expect(page.getByText("La cuota inicial va de 20 % a menos de 100 %.")).toBeVisible();
    await expect(result(page)).toContainText("Revisa los campos marcados");
  });

  for (const [name, viewport] of Object.entries(VIEWPORTS)) {
    test(`with a result has no axe violations at ${name}`, async ({ page }) => {
      await page.setViewportSize(viewport);
      await saveFinances(page, { incomeCop: 8_000_000, savingsCop: 150_000_000 });
      await openCalculator(page);
      await page.getByText("Ajustes del crédito").click();
      await expect(page.getByRole("link", { name: /^Ver \d+ proyectos hasta/ })).toBeVisible();
      await expectNoViolations(page);
    });
  }
});

test.describe("¿Me alcanza?", () => {
  const cases = [
    {
      name: "fits",
      slug: "terrazas-de-santa-maria",
      finances: { incomeCop: 8_000_000, savingsCop: 90_000_000 },
      shows: [/Te alcanza/, /La cuota sería \$\s[\d.]+ al mes/],
    },
    {
      name: "lacks savings",
      slug: "balcones-del-ajizal",
      finances: { incomeCop: 8_000_000, savingsCop: 90_000_000, monthsToDelivery: 24 },
      shows: [/Te faltan \$\s3\.600\.000 de cuota inicial/, /\$\s150\.000 al mes durante los 24 meses/],
    },
    {
      name: "has a payment over the cap",
      slug: "bosque-de-ditaires",
      finances: { incomeCop: 8_000_000, savingsCop: 150_000_000 },
      shows: [/La cuota sería \$\s[\d.]+, el [\d,]+\s% de tu ingreso; el máximo es 40\s%/],
    },
  ];

  for (const { name, slug, finances, shows } of cases) {
    test(`says when the project ${name}`, async ({ page }) => {
      await saveFinances(page, finances);
      await page.goto(`/proyectos/${slug}/`);
      await block(page).scrollIntoViewIfNeeded();
      for (const text of shows) await expect(block(page).getByRole("status")).toContainText(text);
      // For which unit type and with which rate, and where the rate comes from.
      await expect(block(page)).toContainText(/Para .+, desde \$\s[\d,.]+\smillones, observado el/);
      await expect(block(page)).toContainText("licencia CC BY-SA 4.0");
      await expect(block(page)).toContainText(/semana del \d+ \w+ \d{4}/);
      await expect(block(page).getByRole("link", { name: /Superfinanciera/ })).toBeVisible();
    });
  }

  test("asks for income and savings in the block when nothing is saved", async ({ page }) => {
    await page.goto("/proyectos/balcones-del-ajizal/");
    await block(page).scrollIntoViewIfNeeded();
    await hydrated(page);
    await fill(page, "8000000", "90000000");
    await expect(block(page).getByRole("status")).toContainText("Te faltan");
    await page.reload();
    await block(page).scrollIntoViewIfNeeded();
    await expect(block(page).getByRole("button", { name: "Cambiar" })).toBeVisible();
    await block(page).getByRole("button", { name: "Olvidar mis datos" }).click();
    await expect(block(page).getByLabel(INCOME)).toHaveValue("");
  });

  for (const [name, viewport] of Object.entries(VIEWPORTS)) {
    test(`with an answer has no axe violations at ${name}`, async ({ page }) => {
      await page.setViewportSize(viewport);
      await saveFinances(page, { incomeCop: 8_000_000, savingsCop: 90_000_000 });
      await page.goto("/proyectos/balcones-del-ajizal/");
      await block(page).scrollIntoViewIfNeeded();
      await expect(block(page).getByRole("status")).toContainText("Te faltan");
      await expectNoViolations(page);
    });
  }
});

test("no request carries the income or the savings", async ({ page }) => {
  // Figures that no price nor date could contain.
  const income = "8123457";
  const savings = "151234567";
  const sent: string[] = [];
  page.on("request", (request) => sent.push(`${request.url()} ${request.postData() ?? ""}`));

  await openCalculator(page);
  await fill(page, income, savings);
  await page.getByRole("link", { name: /^Ver \d+ proyectos? hasta/ }).click();
  await expect(page.getByRole("heading", { level: 1 })).toContainText("proyecto");
  await page.goto("/proyectos/balcones-del-ajizal/");
  await block(page).scrollIntoViewIfNeeded();
  await expect(block(page).getByRole("status")).toContainText("Te alcanza");
  await page.goto("/comparar/?p=altos-de-niquia,balcones-del-ajizal");
  await expect(page.getByRole("table")).toContainText("Te alcanza");

  const secrets = [income, savings, "8.123.457", "151.234.567", "8%2E123", "151%2E234"];
  expect(sent.length).toBeGreaterThan(10);
  expect(sent.filter((request) => secrets.some((secret) => request.includes(secret)))).toEqual([]);
});
