import { describe, expect, it } from "vitest";

import {
  doneLabel,
  errorView,
  remainingLabel,
  runningLabel,
  stepSummary,
  THINKING,
} from "../../src/lib/advisor/labels";
import { GENERAL_SUGGESTIONS, suggestionsFor } from "../../src/lib/advisor/suggestions";

describe("step labels", () => {
  it("names each tool while it runs and after", () => {
    expect(THINKING).toBe("Pensando…");
    expect(runningLabel("search_projects")).toBe("Buscando proyectos…");
    expect(doneLabel("search_projects")).toBe("Buscó proyectos");
    expect(runningLabel("max_affordable_price")).toBe("Calculando cuánto puedes comprar…");
    expect(doneLabel("down_payment_plan")).toBe("Calculó la cuota inicial");
  });

  it("has a generic label for a tool it does not know, also one named like a prototype key", () => {
    expect(runningLabel("new_tool")).toBe("Consultando datos…");
    expect(doneLabel("constructor")).toBe("Consultó datos");
  });

  it("summarizes the tools of an answer once each, in order", () => {
    const tools = ["search_projects", "get_project", "get_project", "search_projects"];
    expect(stepSummary(tools)).toEqual(["Buscó proyectos", "Revisó un proyecto"]);
  });
});

describe("errorView", () => {
  const now = new Date("2026-11-25T20:00:00Z"); // 3:00 p. m. in Bogotá

  it("counts down the per-minute limit", () => {
    const error = { kind: "rate-minute", retryAfterSeconds: 20 } as const;
    expect(errorView(error, now)).toEqual({
      text: "Vas muy rápido. Podrás preguntar de nuevo en 20 segundos.",
      action: "countdown",
      note: null,
    });
    expect(errorView(error, now, 1).text).toBe(
      "Vas muy rápido. Podrás preguntar de nuevo en 1 segundo.",
    );
  });

  it("says when the daily limit lifts and points to the search", () => {
    const view = errorView({ kind: "rate-day", retryAfterSeconds: 9 * 3600 }, now);
    expect(view.text).toMatch(/^Llegaste al límite de preguntas de hoy\. Podrás seguir mañana/);
    expect(view.text).toMatch(/a las 12:00/);
    expect(view.action).toBe("search");
  });

  it("has the text and action of every other error", () => {
    expect(errorView({ kind: "budget" }, now)).toMatchObject({ action: "search" });
    expect(errorView({ kind: "unavailable" }, now)).toEqual({
      text: "No pude responder esta vez.",
      action: "retry",
      note: null,
    });
    expect(errorView({ kind: "full" }, now)).toEqual({
      text: "Esta conversación llegó a 20 mensajes.",
      action: "new-conversation",
      note: null,
    });
    expect(errorView({ kind: "gone" }, now).action).toBe("continue");
    const connection = errorView({ kind: "connection" }, now);
    expect(connection.text).toBe("Se perdió la conexión antes de la respuesta.");
    expect(connection.action).toBe("retry");
    expect(connection.note).toMatch(/contado/);
  });

  it("never shows the API's English details", () => {
    for (const kind of ["budget", "unavailable", "full", "gone", "connection"] as const) {
      expect(errorView({ kind }, now).text).not.toMatch(/advisor|conversation|request/i);
    }
  });
});

describe("remainingLabel", () => {
  it("shows the count only at 10 or fewer", () => {
    expect(remainingLabel(null)).toBeNull();
    expect(remainingLabel(11)).toBeNull();
    expect(remainingLabel(10)).toBe("Te quedan 10 preguntas hoy");
    expect(remainingLabel(1)).toBe("Te queda 1 pregunta hoy");
    expect(remainingLabel(0)).toBe("No te quedan preguntas hoy");
  });
});

describe("suggestionsFor", () => {
  it("suggests the general questions without a project", () => {
    expect(suggestionsFor(null)).toEqual([...GENERAL_SUGGESTIONS]);
    expect(GENERAL_SUGGESTIONS.length).toBeGreaterThanOrEqual(3);
    expect(GENERAL_SUGGESTIONS.length).toBeLessThanOrEqual(5);
  });

  it("names the project and its municipality", () => {
    expect(suggestionsFor({ name: "Arrayanes del Sur", municipality: "la_estrella" })).toEqual([
      "¿Cuánto ha subido Arrayanes del Sur?",
      "¿Cuánto pagaría al mes de cuota inicial en Arrayanes del Sur?",
      "Compara Arrayanes del Sur con otros proyectos de La Estrella",
    ]);
  });
});
