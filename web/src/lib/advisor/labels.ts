/**
 * The advisor page's fixed texts (SPEC 11c §6): the steps while a reply runs and in its
 * summary, the errors, the notice under the composer and the count of messages left.
 */
import { formatRetryAt } from "../format";
import type { AdvisorError } from "./stream";

/** Before the first step arrives. */
export const THINKING = "Pensando…";

type StepLabels = { running: string; done: string };

// A Map, not an object: a tool called "constructor" must not find Object's prototype.
const STEPS = new Map<string, StepLabels>([
  ["search_projects", { running: "Buscando proyectos…", done: "Buscó proyectos" }],
  ["get_project", { running: "Revisando el proyecto…", done: "Revisó un proyecto" }],
  ["compare_projects", { running: "Comparando proyectos…", done: "Comparó proyectos" }],
  ["list_developers", { running: "Revisando constructoras…", done: "Revisó constructoras" }],
  ["simulate_mortgage", { running: "Simulando el crédito…", done: "Simuló el crédito" }],
  [
    "max_affordable_price",
    { running: "Calculando cuánto puedes comprar…", done: "Calculó cuánto puedes comprar" },
  ],
  [
    "down_payment_plan",
    { running: "Calculando la cuota inicial…", done: "Calculó la cuota inicial" },
  ],
]);

const OTHER_STEP: StepLabels = { running: "Consultando datos…", done: "Consultó datos" };

/** What a tool is doing while it runs: "Buscando proyectos…". */
export function runningLabel(tool: string): string {
  return (STEPS.get(tool) ?? OTHER_STEP).running;
}

/** What a tool did, for the summary of an answer: "Buscó proyectos". */
export function doneLabel(tool: string): string {
  return (STEPS.get(tool) ?? OTHER_STEP).done;
}

/** The summary of the tools an answer used, each once, in order: ["Buscó proyectos", …]. */
export function stepSummary(tools: readonly string[]): string[] {
  return [...new Set(tools.map(doneLabel))];
}

export const NOTICE =
  "Respondo con los precios que publican las constructoras. No es asesoría financiera ni una " +
  "oferta. No escribas datos personales.";

/** What the page does about an error, besides showing its text. */
export type ErrorAction =
  | "countdown" // the send button waits for the limit to lift
  | "search" // link "Seguir con la búsqueda" to /proyectos/
  | "retry" // button "Reintentar", sends the same question again
  | "new-conversation" // button "Nueva consulta" with the question already written
  | "continue" // the page goes on by itself in a new conversation
  | null;

export type ErrorView = { text: string; action: ErrorAction; note: string | null };

/**
 * The text and action of an error. secondsLeft is the countdown of the per-minute limit; now
 * sets when the daily limit lifts.
 */
export function errorView(
  error: AdvisorError,
  now: Date = new Date(),
  secondsLeft?: number,
): ErrorView {
  switch (error.kind) {
    case "rate-minute": {
      const seconds = Math.max(0, Math.ceil(secondsLeft ?? error.retryAfterSeconds));
      const unit = seconds === 1 ? "segundo" : "segundos";
      return {
        text: `Vas muy rápido. Podrás preguntar de nuevo en ${seconds} ${unit}.`,
        action: "countdown",
        note: null,
      };
    }
    case "rate-day":
      return {
        text:
          "Llegaste al límite de preguntas de hoy. " +
          `Podrás seguir ${formatRetryAt(error.retryAfterSeconds, now)}.`,
        action: "search",
        note: null,
      };
    case "budget":
      return {
        text:
          "El asesor ya respondió todo lo que podía hoy. " +
          "Vuelve mañana; la búsqueda sigue funcionando.",
        action: "search",
        note: null,
      };
    case "full":
      return {
        text: "Esta conversación llegó a 20 mensajes.",
        action: "new-conversation",
        note: null,
      };
    case "gone":
      return {
        text:
          "Esta conversación ya no existe en el servidor. " +
          "Tu pregunta va en una conversación nueva.",
        action: "continue",
        note: null,
      };
    case "connection":
      return {
        text: "Se perdió la conexión antes de la respuesta.",
        action: "retry",
        note: "Es posible que la pregunta ya se haya contado en tu límite de hoy.",
      };
    case "unavailable":
      return { text: "No pude responder esta vez.", action: "retry", note: null };
    case "busy":
      return { text: "", action: null, note: null };
  }
}

/** Shown when this many messages or fewer are left today. */
export const REMAINING_THRESHOLD = 10;

/** "Te quedan 4 preguntas hoy", only at REMAINING_THRESHOLD or fewer; else null. */
export function remainingLabel(remainingToday: number | null): string | null {
  if (remainingToday === null || remainingToday > REMAINING_THRESHOLD) return null;
  if (remainingToday === 0) return "No te quedan preguntas hoy";
  if (remainingToday === 1) return "Te queda 1 pregunta hoy";
  return `Te quedan ${remainingToday} preguntas hoy`;
}

/** Notices about where the conversations are kept. */
export const STORAGE_TEXTS = {
  keepToggle: "Conservar mis conversaciones en este navegador",
  clearButton: "Borrar mis conversaciones",
  clearHint:
    "Se borran de este navegador. En el servidor se borran solas a los 7 días sin actividad.",
  autoDeleteHint: "Las conversaciones se borran de este navegador a los 7 días sin actividad.",
  memoryOnly:
    "Este navegador no deja guardar conversaciones; la actual se pierde al cerrar la página.",
  dropped: "Se borró tu conversación más vieja para guardar esta: el límite es de 30.",
} as const;
