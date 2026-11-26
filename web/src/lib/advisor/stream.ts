/**
 * Client of POST /advisor/chat/stream (SPEC 11c §3): sends one message, reads the Server-Sent
 * Events with fetch and a ReadableStream, validates each one and turns every failure into one
 * of the errors of §6.
 *
 * The events are not in openapi.json (FastAPI documents SSE generically), so their shapes are
 * checked here by hand. Their source is StepOut, StreamAnswerOut and StreamErrorOut in
 * src/sobreplano/interface/api/routes/advisor.py.
 */
import { createParser, type EventSourceMessage } from "eventsource-parser";

import type { components } from "../api/schema";

type ChatIn = components["schemas"]["ChatIn"];

export type StepPhase = "start" | "end";
export type AdvisorStep = { tool: string; phase: StepPhase };

export type AdvisorAnswer = {
  threadId: string;
  reply: string;
  toolsUsed: string[];
  /** Slugs the reply names, in order. */
  projects: string[];
  /** Messages left today; null when the API does not count them. */
  remainingToday: number | null;
};

/** The failures of §6, by what the page does about them. */
export type AdvisorError =
  /** 429 that lifts within a minute: the send button waits for it. */
  | { kind: "rate-minute"; retryAfterSeconds: number }
  /** 429 that lifts later, at Bogotá midnight. */
  | { kind: "rate-day"; retryAfterSeconds: number }
  /** 503: the day's budget is spent. */
  | { kind: "budget" }
  /** 503 for another reason, an `error` event or an answer the page cannot read. */
  | { kind: "unavailable" }
  /** 409: the conversation has its 20 messages. */
  | { kind: "full" }
  /** 404: the server no longer has the conversation. */
  | { kind: "gone" }
  /** The request failed or the stream ended before the answer; it may have been counted. */
  | { kind: "connection" }
  /** Another message is still in flight; nothing was sent. */
  | { kind: "busy" };

export type StreamResult = { ok: true; answer: AdvisorAnswer } | { ok: false; error: AdvisorError };

export type SendOptions = {
  message: string;
  threadId: string | null;
  onStep?: (step: AdvisorStep) => void;
};

/** The longest wait that still counts as the per-minute limit. */
export const MINUTE_RETRY_LIMIT_SECONDS = 60;
export const BUDGET_DETAIL = "advisor budget exhausted for today";

/**
 * A client that allows one message in flight at a time: while one streams, `send` answers
 * `busy` without a request.
 */
export class AdvisorClient {
  readonly #url: string;
  readonly #fetch: typeof fetch;
  #busy = false;

  constructor(baseUrl: string, fetchImpl: typeof fetch = (...args) => fetch(...args)) {
    this.#url = `${baseUrl.replace(/\/+$/, "")}/advisor/chat/stream`;
    this.#fetch = fetchImpl;
  }

  get busy(): boolean {
    return this.#busy;
  }

  /** Send one message and resolve with its answer or its error; never rejects. */
  async send(options: SendOptions): Promise<StreamResult> {
    if (this.#busy) return failure({ kind: "busy" });
    this.#busy = true;
    try {
      return await this.#send(options);
    } finally {
      this.#busy = false;
    }
  }

  async #send({ message, threadId, onStep }: SendOptions): Promise<StreamResult> {
    const body: ChatIn = { message, thread_id: threadId };
    let response: Response;
    try {
      response = await this.#fetch(this.#url, {
        method: "POST",
        headers: { "content-type": "application/json", accept: "text/event-stream" },
        body: JSON.stringify(body),
      });
    } catch {
      return failure({ kind: "connection" });
    }
    if (!response.ok) return failure(await httpError(response));
    const type = response.headers.get("content-type") ?? "";
    if (!type.startsWith("text/event-stream") || response.body === null) {
      return failure({ kind: "unavailable" });
    }
    return readEvents(response.body, onStep);
  }
}

/** Read the stream until its `answer` or `error`; a stream that ends before is `connection`. */
async function readEvents(
  body: ReadableStream<Uint8Array>,
  onStep: ((step: AdvisorStep) => void) | undefined,
): Promise<StreamResult> {
  let result: StreamResult | null = null;
  const parser = createParser({
    onEvent(event) {
      if (result === null) result = handleEvent(event, onStep);
    },
  });
  const reader = body.getReader();
  const decoder = new TextDecoder();
  try {
    while (result === null) {
      const { done, value } = await reader.read();
      if (done) break;
      // stream: true keeps a character split between two chunks whole.
      parser.feed(decoder.decode(value, { stream: true }));
    }
  } catch {
    return result ?? failure({ kind: "connection" });
  } finally {
    // The answer is the last event; nothing after it matters.
    reader.cancel().catch(() => {});
  }
  return result ?? failure({ kind: "connection" });
}

/** The result an event ends the stream with, or null for a step or an unknown event. */
function handleEvent(
  event: EventSourceMessage,
  onStep: ((step: AdvisorStep) => void) | undefined,
): StreamResult | null {
  if (event.event !== "step" && event.event !== "answer" && event.event !== "error") {
    return null; // newer servers may add events; this page ignores them
  }
  let data: unknown;
  try {
    data = JSON.parse(event.data);
  } catch {
    return failure({ kind: "unavailable" });
  }
  if (event.event === "step") {
    const step = parseStep(data);
    if (step === null) return failure({ kind: "unavailable" });
    onStep?.(step);
    return null;
  }
  if (event.event === "answer") {
    const answer = parseAnswer(data);
    return answer === null ? failure({ kind: "unavailable" }) : { ok: true, answer };
  }
  if (isRecord(data) && typeof data.status === "number" && typeof data.detail === "string") {
    return failure(errorFor(data.status, data.detail, null));
  }
  return failure({ kind: "unavailable" });
}

async function httpError(response: Response): Promise<AdvisorError> {
  let detail: unknown = null;
  try {
    detail = ((await response.json()) as { detail?: unknown }).detail;
  } catch {
    // A body that is not JSON (a proxy's page) still has a status.
  }
  const retryAfter = Number.parseInt(response.headers.get("retry-after") ?? "", 10);
  return errorFor(response.status, detail, Number.isFinite(retryAfter) ? retryAfter : null);
}

/** The §6 error of a status and detail, the same for an HTTP answer and an `error` event. */
export function errorFor(
  status: number,
  detail: unknown,
  retryAfterSeconds: number | null,
): AdvisorError {
  if (status === 429) {
    // Without Retry-After, assume the short wait: the page can always try again.
    const seconds = Math.max(1, retryAfterSeconds ?? MINUTE_RETRY_LIMIT_SECONDS);
    return seconds <= MINUTE_RETRY_LIMIT_SECONDS
      ? { kind: "rate-minute", retryAfterSeconds: seconds }
      : { kind: "rate-day", retryAfterSeconds: seconds };
  }
  if (status === 409) return { kind: "full" };
  if (status === 404) return { kind: "gone" };
  if (status === 503 && detail === BUDGET_DETAIL) return { kind: "budget" };
  return { kind: "unavailable" };
}

function parseStep(data: unknown): AdvisorStep | null {
  if (!isRecord(data) || typeof data.tool !== "string") return null;
  if (data.phase !== "start" && data.phase !== "end") return null;
  return { tool: data.tool, phase: data.phase };
}

function parseAnswer(data: unknown): AdvisorAnswer | null {
  if (!isRecord(data)) return null;
  const { thread_id, reply, tools_used, projects, remaining_today } = data;
  if (typeof thread_id !== "string" || thread_id === "" || typeof reply !== "string") return null;
  if (!isStringArray(tools_used) || !isStringArray(projects)) return null;
  let remaining: number | null = null;
  if (remaining_today !== null && remaining_today !== undefined) {
    if (typeof remaining_today !== "number" || !Number.isInteger(remaining_today)) return null;
    if (remaining_today < 0) return null;
    remaining = remaining_today;
  }
  return {
    threadId: thread_id,
    reply,
    toolsUsed: tools_used,
    projects,
    remainingToday: remaining,
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function failure(error: AdvisorError): StreamResult {
  return { ok: false, error };
}
