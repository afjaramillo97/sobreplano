// The advisor page (SPEC 11c) with POST /advisor/chat/stream simulated: page.route answers
// with fixed SSE bodies, so no test reaches the API or the model. The live steps need a body
// that arrives in parts, which route.fulfill cannot send, so that test swaps fetch instead.
import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test, VIEWPORTS } from "./fixtures";

const ADVISOR = "/asesor/";
const STREAM = "**/advisor/chat/stream";
const THREAD = "6f1c2b9e-1d1e-4c55-9c1b-0b8a4f1d2e3f";
const THREAD_2 = "0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d";
const NOW = new Date("2026-11-25T15:00:00-05:00");

const REPLY = `Encontré dos proyectos en Itagüí:

| Proyecto | Desde |
| --- | --- |
| Reserva de San Antonio | $ 289 M |
| Bosque de Ditaires | $ 265 M |

Mira la [ficha](/proyectos/bosque-de-ditaires/), la [constructora](https://example.com/piedra/bosque-de-ditaires) o [este sitio](https://evil.example/oferta).

<script>window.__pwned = true</script><img src=x onerror="window.__pwned = true">`;

type Answer = { thread_id?: string; reply?: string; projects?: string[]; remaining_today?: number | null };

function sse(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

function answerBody(answer: Answer = {}): string {
  return (
    sse("step", { tool: "search_projects", phase: "start" }) +
    sse("step", { tool: "search_projects", phase: "end" }) +
    sse("answer", {
      thread_id: answer.thread_id ?? THREAD,
      reply: answer.reply ?? REPLY,
      tools_used: ["search_projects"],
      projects: answer.projects ?? ["reserva-de-san-antonio", "bosque-de-ditaires"],
      remaining_today: answer.remaining_today === undefined ? 27 : answer.remaining_today,
    })
  );
}

type Reply = { status?: number; body: string; headers?: Record<string, string> };

/** Answers each stream request with the next reply (the last one repeats); records the bodies. */
async function routeStream(page: Page, replies: Reply[]) {
  const requests: { message: string; thread_id: string | null }[] = [];
  await page.route(STREAM, async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    requests.push(route.request().postDataJSON());
    const reply = replies[Math.min(requests.length - 1, replies.length - 1)] as Reply;
    const status = reply.status ?? 200;
    await route.fulfill({
      status,
      headers: {
        "content-type": status === 200 ? "text/event-stream" : "application/json",
        "access-control-allow-origin": "*",
        "access-control-expose-headers": "Retry-After",
        ...reply.headers,
      },
      body: reply.body,
    });
  });
  return requests;
}

const ok = (answer?: Answer): Reply => ({ body: answerBody(answer) });
const refused = (status: number, detail: string, headers?: Record<string, string>): Reply => ({
  status,
  body: JSON.stringify({ detail }),
  ...(headers ? { headers } : {}),
});

/** Waits for the island to hydrate: typed before that, the text would be lost. */
async function hydrated(page: Page) {
  await expect(page.locator("astro-island[ssr]")).toHaveCount(0);
}

/** Opens a page of the advisor, ready to be used. */
async function open(page: Page, path: string) {
  await page.goto(path);
  await hydrated(page);
}

async function ask(page: Page, question: string) {
  await hydrated(page);
  await page.getByLabel("Tu pregunta para el asesor").fill(question);
  await page.getByLabel("Tu pregunta para el asesor").press("Enter");
}

const log = (page: Page) => page.getByRole("log", { name: "Conversación con el asesor" });
const alert = (page: Page) => page.getByRole("alert");

async function expectNoViolations(page: Page) {
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(", ")}`)).toEqual([]);
}

/** Stores one conversation in the page's localStorage before it loads. */
async function seedConversation(page: Page, updatedAt: string, keepHistory = false) {
  await page.addInitScript(
    ([id, at, keep]) => {
      const conversation = {
        id,
        title: "¿Qué hay en Itagüí?",
        projectSlug: null,
        messages: [
          { role: "user", text: "¿Qué hay en Itagüí?", at },
          { role: "advisor", text: "Hay dos proyectos.", tools: [], projects: [], at },
        ],
        updatedAt: at,
        closed: false,
      };
      if (!localStorage.getItem("sobreplano.asesor.v1")) {
        localStorage.setItem(
          "sobreplano.asesor.v1",
          JSON.stringify({ keepHistory: keep, conversations: [conversation] }),
        );
      }
    },
    [THREAD, updatedAt, keepHistory] as const,
  );
}

test.describe("the advisor page", () => {
  test("a suggested question shows Pensando…, the steps live, the answer and two cards", async ({ page }) => {
    // The body arrives in parts, as the server sends it.
    await page.addInitScript((body) => {
      const original = window.fetch;
      window.fetch = async (input, init) => {
        if (!String(input).endsWith("/advisor/chat/stream")) return original(input, init);
        const parts = body as string[];
        const encoder = new TextEncoder();
        const stream = new ReadableStream<Uint8Array>({
          async start(controller) {
            for (const part of parts) {
              await new Promise((resolve) => setTimeout(resolve, 600));
              controller.enqueue(encoder.encode(part));
            }
            controller.close();
          },
        });
        return new Response(stream, { headers: { "content-type": "text/event-stream" } });
      };
    }, answerBody().split(/(?<=\n\n)/));
    await open(page, ADVISOR);

    await page.getByRole("button", { name: /Itagüí por menos de 300 millones/ }).click();
    await expect(page.getByText("Pensando…")).toBeVisible();
    await expect(page.getByText("Buscando proyectos…")).toBeVisible();
    await expect(page.getByText("Buscó proyectos").first()).toBeVisible();

    await expect(log(page).getByRole("table")).toBeVisible();
    const cards = log(page).getByRole("list", { name: "Proyectos de esta respuesta" }).getByRole("link");
    await expect(cards).toHaveCount(2);
    await expect(cards.first()).toHaveAttribute("href", "/proyectos/reserva-de-san-antonio/");
    await expect(page).toHaveURL(new RegExp(`\\?c=${THREAD}$`));
  });

  test("links: the site's and the developers' stay, any other is text; HTML is never rendered", async ({ page }) => {
    await routeStream(page, [ok()]);
    await open(page, ADVISOR);
    await ask(page, "¿Qué hay en Itagüí?");
    await expect(log(page).getByRole("table")).toBeVisible();

    await expect(log(page).getByRole("link", { name: "ficha" })).toHaveAttribute("href", "/proyectos/bosque-de-ditaires/");
    const developer = log(page).getByRole("link", { name: /constructora/ });
    await expect(developer).toHaveAttribute("target", "_blank");
    await expect(developer).toHaveAttribute("rel", "noopener noreferrer");
    await expect(log(page).getByText("este sitio")).toBeVisible();
    await expect(log(page).locator('a[href*="evil.example"]')).toHaveCount(0);
    await expect(log(page).locator("script, img")).toHaveCount(0);
    expect(await page.evaluate(() => (window as { __pwned?: boolean }).__pwned)).toBeUndefined();
  });

  test("a second message goes in the same conversation", async ({ page }) => {
    const requests = await routeStream(page, [ok()]);
    await open(page, ADVISOR);
    await ask(page, "Primera");
    await expect(log(page).getByRole("table")).toBeVisible();
    await ask(page, "Segunda");
    await expect(log(page).getByText("Segunda")).toBeVisible();
    await expect(log(page).getByRole("table")).toHaveCount(2);
    expect(requests.map((r) => r.thread_id)).toEqual([null, THREAD]);
  });

  test("a reload brings the conversation back, and the next question carries its thread", async ({ page }) => {
    const requests = await routeStream(page, [ok()]);
    await open(page, ADVISOR);
    await ask(page, "¿Qué hay en Itagüí?");
    await expect(page).toHaveURL(new RegExp(`\\?c=${THREAD}$`));
    await page.reload();
    await hydrated(page);
    await expect(log(page).getByText("¿Qué hay en Itagüí?").first()).toBeVisible();
    await expect(log(page).getByRole("table")).toBeVisible();
    await ask(page, "¿Y la más barata?");
    await expect(log(page).getByText("¿Y la más barata?")).toBeVisible();
    expect(requests.at(-1)?.thread_id).toBe(THREAD);
  });

  test("from a project page, the advisor opens with the project and its questions", async ({ page }) => {
    await page.goto("/proyectos/bosque-de-ditaires/");
    await page.getByRole("link", { name: "Pregúntale al asesor" }).click();
    await expect(page).toHaveURL(/\/asesor\/\?proyecto=bosque-de-ditaires$/);
    await hydrated(page);
    await page.setViewportSize(VIEWPORTS.desktop);
    await expect(page.getByRole("heading", { name: "Bosque de Ditaires", exact: true })).toBeVisible();
    const questions = page.getByRole("list", { name: "Preguntas sugeridas" }).getByRole("button");
    await expect(questions).toHaveCount(3);
    for (const question of await questions.allTextContents()) expect(question).toContain("Bosque de Ditaires");
  });

  test("a 429 of the minute counts down, then lets the person send again", async ({ page }) => {
    await page.clock.install({ time: NOW });
    await routeStream(page, [refused(429, "too many requests", { "Retry-After": "20" }), ok()]);
    await open(page, ADVISOR);
    await ask(page, "Hola");
    await expect(alert(page)).toContainText("Vas muy rápido. Podrás preguntar de nuevo en 20 segundos.");
    const send = page.getByRole("button", { name: "Enviar" });
    await expect(send).toBeDisabled();
    await expect(page.getByLabel("Tu pregunta para el asesor")).toHaveValue("Hola");
    await page.clock.runFor(10_000);
    await expect(alert(page)).toContainText("en 10 segundos");
    await page.clock.runFor(11_000);
    await expect(alert(page)).toHaveCount(0);
    await expect(send).toBeEnabled();
  });

  test("a 429 of the day says when it lifts and points to the search", async ({ page }) => {
    await routeStream(page, [refused(429, "too many requests", { "Retry-After": "3600" })]);
    await open(page, ADVISOR);
    await ask(page, "Hola");
    await expect(alert(page)).toContainText("Llegaste al límite de preguntas de hoy. Podrás seguir");
    await expect(alert(page).getByRole("link", { name: "Seguir con la búsqueda" })).toHaveAttribute("href", "/proyectos/");
    await expect(alert(page).getByRole("link", { name: "Probar la calculadora" })).toHaveAttribute("href", "/calculadora/");
  });

  test("a 503 for the budget says to come back tomorrow", async ({ page }) => {
    await routeStream(page, [refused(503, "advisor budget exhausted for today")]);
    await open(page, ADVISOR);
    await ask(page, "Hola");
    await expect(alert(page)).toContainText("El asesor ya respondió todo lo que podía hoy.");
    await expect(alert(page).getByRole("link", { name: "Seguir con la búsqueda" })).toBeVisible();
    await expect(alert(page).getByRole("link", { name: "Probar la calculadora" })).toBeVisible();
    await expect(alert(page)).not.toContainText("advisor");
  });

  test("a 409 offers a new conversation with the question already written", async ({ page }) => {
    await seedConversation(page, NOW.toISOString());
    await routeStream(page, [refused(409, "conversation limit reached")]);
    await open(page, `${ADVISOR}?c=${THREAD}`);
    await ask(page, "Una más");
    await expect(alert(page)).toContainText("Esta conversación llegó a 20 mensajes.");
    await alert(page).getByRole("button", { name: "Nueva consulta" }).click();
    await expect(page.getByLabel("Tu pregunta para el asesor")).toHaveValue("Una más");
    await expect(page).toHaveURL(/\/asesor\/$/);
  });

  test("a 404 goes on by itself in a new conversation", async ({ page }) => {
    await seedConversation(page, NOW.toISOString());
    const requests = await routeStream(page, [
      refused(404, "conversation not found"),
      ok({ thread_id: THREAD_2 }),
    ]);
    await open(page, `${ADVISOR}?c=${THREAD}`);
    await ask(page, "¿Sigue disponible?");
    await expect(alert(page)).toContainText("Esta conversación ya no existe en el servidor.");
    await expect(page).toHaveURL(new RegExp(`\\?c=${THREAD_2}$`));
    await expect(log(page).getByRole("table")).toBeVisible();
    expect(requests.map((r) => r.thread_id)).toEqual([THREAD, null]);
  });

  test("a stream cut after a step offers to retry, and the composer works again", async ({ page }) => {
    const requests = await routeStream(page, [
      { body: sse("step", { tool: "search_projects", phase: "start" }) },
      ok(),
    ]);
    await open(page, ADVISOR);
    await ask(page, "Hola");
    await expect(alert(page)).toContainText("Se perdió la conexión antes de la respuesta.");
    await alert(page).getByRole("button", { name: "Reintentar" }).click();
    await expect(log(page).getByRole("table")).toBeVisible();
    expect(requests.map((r) => r.message)).toEqual(["Hola", "Hola"]);
    await expect(page.getByLabel("Tu pregunta para el asesor")).toBeEnabled();
  });

  test("while a reply runs, the send button is off and Enter sends nothing more", async ({ page }) => {
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    let count = 0;
    await page.route(STREAM, async (route) => {
      count += 1;
      await gate;
      await route.fulfill({ headers: { "content-type": "text/event-stream" }, body: answerBody() });
    });
    await open(page, ADVISOR);
    await ask(page, "Primera");
    await expect(page.getByText("Pensando…")).toBeVisible();
    await expect(page.getByRole("button", { name: "Enviar" })).toBeDisabled();
    await page.getByLabel("Tu pregunta para el asesor").fill("Segunda");
    await page.getByLabel("Tu pregunta para el asesor").press("Enter");
    release();
    await expect(log(page).getByRole("table")).toBeVisible();
    expect(count).toBe(1);
  });

  test("the remaining count shows only at 10 or fewer", async ({ page }) => {
    await routeStream(page, [ok({ remaining_today: 11 }), ok({ remaining_today: 4 })]);
    await open(page, ADVISOR);
    await ask(page, "Una");
    await expect(log(page).getByRole("table")).toBeVisible();
    await expect(page.getByTestId("remaining")).toHaveCount(0);
    await ask(page, "Dos");
    await expect(page.getByTestId("remaining")).toHaveText("Te quedan 4 preguntas hoy");
  });
});

test.describe("the conversations in the browser", () => {
  test("one inactive for 8 days disappears", async ({ page }) => {
    await page.clock.setFixedTime(NOW);
    await seedConversation(page, new Date(NOW.getTime() - 8 * 86_400_000).toISOString());
    await open(page, ADVISOR);
    await page.setViewportSize(VIEWPORTS.desktop);
    await expect(page.getByText("Todavía no tienes conversaciones en este navegador.")).toBeVisible();
  });

  test("with 'Conservar' on, it stays", async ({ page }) => {
    await page.clock.setFixedTime(NOW);
    await seedConversation(page, new Date(NOW.getTime() - 8 * 86_400_000).toISOString(), true);
    await open(page, ADVISOR);
    await page.setViewportSize(VIEWPORTS.desktop);
    const list = page.getByRole("complementary", { name: "Tus conversaciones" });
    await expect(list.getByRole("button", { name: /¿Qué hay en Itagüí\?/ })).toBeVisible();
    await expect(list.getByRole("switch", { name: /Conservar mis conversaciones/ })).toBeChecked();
  });

  test("the switch turns the deletion off, and 'Borrar mis conversaciones' empties the list", async ({ page }) => {
    await seedConversation(page, NOW.toISOString());
    await open(page, ADVISOR);
    await page.setViewportSize(VIEWPORTS.desktop);
    const list = page.getByRole("complementary", { name: "Tus conversaciones" });
    const keep = list.getByRole("switch", { name: /Conservar mis conversaciones/ });
    await keep.click();
    await expect(keep).toBeChecked();
    expect(await page.evaluate(() => JSON.parse(localStorage.getItem("sobreplano.asesor.v1") ?? "{}").keepHistory)).toBe(true);

    await list.getByRole("button", { name: "Borrar mis conversaciones" }).click();
    await list.getByRole("button", { name: "Sí, borrar" }).click();
    await expect(list.getByText("Todavía no tienes conversaciones en este navegador.")).toBeVisible();
    expect(await page.evaluate(() => JSON.parse(localStorage.getItem("sobreplano.asesor.v1") ?? "{}").conversations)).toEqual([]);
  });
});

test.describe("on a phone", () => {
  test.use({ viewport: VIEWPORTS.mobile });

  test("the conversations and the project open as sheets", async ({ page }) => {
    await seedConversation(page, NOW.toISOString());
    await open(page, `${ADVISOR}?c=${THREAD}`);
    await page.getByRole("button", { name: "Tus conversaciones" }).click();
    const list = page.getByRole("dialog", { name: "Tus conversaciones" });
    await expect(list.getByRole("button", { name: /¿Qué hay en Itagüí\?/ })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(list).toBeHidden();
    await page.getByRole("button", { name: "Proyectos en esta conversación" }).click();
    await expect(page.getByRole("dialog", { name: "Proyectos" })).toBeVisible();
  });
});

test.describe("accessibility", () => {
  for (const [viewportName, viewport] of Object.entries(VIEWPORTS)) {
    test.describe(`at ${viewportName}`, () => {
      test.use({ viewport });

      test("empty, with a conversation and with an error, axe finds nothing", async ({ page }) => {
        await routeStream(page, [ok(), refused(503, "advisor unavailable")]);
        await open(page, ADVISOR);
        await expectNoViolations(page);
        await ask(page, "¿Qué hay en Itagüí?");
        await expect(log(page).getByRole("table")).toBeVisible();
        await expectNoViolations(page);
        await ask(page, "Otra");
        await expect(alert(page)).toContainText("No pude responder esta vez.");
        await expectNoViolations(page);
      });

      if (viewport.width < 1024) {
        test("each sheet open, axe finds nothing", async ({ page }) => {
          await seedConversation(page, NOW.toISOString());
          await open(page, `${ADVISOR}?c=${THREAD}`);
          await page.getByRole("button", { name: "Tus conversaciones" }).click();
          await expect(page.getByRole("dialog", { name: "Tus conversaciones" })).toBeVisible();
          await expectNoViolations(page);
          await page.keyboard.press("Escape");
          await page.getByRole("button", { name: "Proyectos en esta conversación" }).click();
          await expect(page.getByRole("dialog", { name: "Proyectos" })).toBeVisible();
          await expectNoViolations(page);
        });
      }
    });
  }

  test("the keyboard reaches the list, the suggestions, the composer, the cards and the panel", async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await routeStream(page, [ok()]);
    await open(page, ADVISOR);
    await expect(page.getByLabel("Tu pregunta para el asesor")).toBeFocused();
    // The suggestions sit just before the composer.
    await page.keyboard.press("Shift+Tab");
    await expect(page.getByRole("button", { name: /qué puedo comprar/ })).toBeFocused();
    await ask(page, "¿Qué hay en Itagüí?");
    await expect(log(page).getByRole("table")).toBeVisible();

    const reached = new Set<string>();
    for (let i = 0; i < 60; i += 1) {
      await page.keyboard.press("Tab");
      const where = await page.evaluate(() => {
        const el = document.activeElement as HTMLElement | null;
        if (!el || el === document.body) return "";
        const outline = getComputedStyle(el).outlineStyle;
        const container = el.closest("aside[aria-label], [role=log]");
        return `${container?.getAttribute("aria-label") ?? ""}|${outline}|${el.tagName}`;
      });
      reached.add(where);
    }
    const areas = [...reached].join("\n");
    expect(areas).toContain("Tus conversaciones|solid");
    expect(areas).toContain("Proyecto|solid");
    expect(areas).toMatch(/Conversación con el asesor\|solid\|A/);
  });
});
