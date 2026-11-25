import { describe, expect, it, vi } from "vitest";

import {
  AdvisorClient,
  BUDGET_DETAIL,
  errorFor,
  type AdvisorStep,
} from "../../src/lib/advisor/stream";

const API = "http://localhost:8000";
const THREAD = "6f1c2b9e-1d1e-4c55-9c1b-0b8a4f1d2e3f";
const ANSWER = {
  thread_id: THREAD,
  reply: "Arrayanes del Sur es el más barato.",
  tools_used: ["search_projects"],
  projects: ["arrayanes-del-sur"],
  remaining_today: 27,
};

function sse(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${typeof data === "string" ? data : JSON.stringify(data)}\n\n`;
}

/** A body that sends each chunk as it is, split where the test says. */
function bodyOf(chunks: string[], { cutAfter = false } = {}): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      if (cutAfter) controller.error(new TypeError("network error"));
      else controller.close();
    },
  });
}

function streamResponse(chunks: string[], options?: { cutAfter?: boolean }): Response {
  return new Response(bodyOf(chunks, options), {
    status: 200,
    headers: { "content-type": "text/event-stream; charset=utf-8" },
  });
}

function jsonResponse(status: number, body: unknown, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", ...headers },
  });
}

function clientAnswering(response: Response | Error) {
  const requests: { url: string; init: RequestInit | undefined }[] = [];
  const fetchImpl = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    requests.push({ url: String(url), init });
    if (response instanceof Error) throw response;
    return response;
  });
  return { client: new AdvisorClient(`${API}/`, fetchImpl as typeof fetch), requests };
}

describe("AdvisorClient.send", () => {
  it("posts the message, reports each step and resolves with the answer", async () => {
    const { client, requests } = clientAnswering(
      streamResponse([
        sse("step", { tool: "search_projects", phase: "start" }),
        ": ping\n\n",
        sse("step", { tool: "search_projects", phase: "end" }),
        sse("answer", ANSWER),
      ]),
    );
    const steps: AdvisorStep[] = [];

    const onStep = (step: AdvisorStep) => steps.push(step);
    const result = await client.send({ message: "Hola", threadId: null, onStep });

    expect(requests).toHaveLength(1);
    expect(requests[0]?.url).toBe(`${API}/advisor/chat/stream`);
    expect(requests[0]?.init?.method).toBe("POST");
    const sent = JSON.parse(String(requests[0]?.init?.body));
    expect(sent).toEqual({ message: "Hola", thread_id: null });
    expect(steps).toEqual([
      { tool: "search_projects", phase: "start" },
      { tool: "search_projects", phase: "end" },
    ]);
    expect(result).toEqual({
      ok: true,
      answer: {
        threadId: THREAD,
        reply: ANSWER.reply,
        toolsUsed: ["search_projects"],
        projects: ["arrayanes-del-sur"],
        remainingToday: 27,
      },
    });
  });

  it("reads events split across chunks, even inside a multibyte character", async () => {
    const whole = sse("answer", { ...ANSWER, reply: "Envigado está más caro." });
    const bytes = new TextEncoder().encode(whole);
    const cut = whole.indexOf("á") + 1; // between the two bytes of "á"
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(bytes.slice(0, cut));
        controller.enqueue(bytes.slice(cut));
        controller.close();
      },
    });
    const { client } = clientAnswering(
      new Response(body, { headers: { "content-type": "text/event-stream" } }),
    );
    const result = await client.send({ message: "Hola", threadId: THREAD });
    expect(result.ok && result.answer.reply).toBe("Envigado está más caro.");
  });

  it("sends the thread id of a conversation that goes on", async () => {
    const { client, requests } = clientAnswering(streamResponse([sse("answer", ANSWER)]));
    await client.send({ message: "¿Y el otro?", threadId: THREAD });
    expect(JSON.parse(String(requests[0]?.init?.body)).thread_id).toBe(THREAD);
  });

  it("ignores an unknown event", async () => {
    const { client } = clientAnswering(
      streamResponse([sse("usage", { tokens: 3 }), sse("answer", ANSWER)]),
    );
    expect((await client.send({ message: "Hola", threadId: null })).ok).toBe(true);
  });

  it("accepts a null remaining_today", async () => {
    const { client } = clientAnswering(
      streamResponse([sse("answer", { ...ANSWER, remaining_today: null })]),
    );
    const result = await client.send({ message: "Hola", threadId: null });
    expect(result.ok && result.answer.remainingToday).toBeNull();
  });

  it.each([
    ["invalid JSON", sse("answer", "{not json")],
    ["an answer without reply", sse("answer", { ...ANSWER, reply: undefined })],
    ["projects that are not strings", sse("answer", { ...ANSWER, projects: [1] })],
    ["a negative remaining_today", sse("answer", { ...ANSWER, remaining_today: -1 })],
    ["a step with an unknown phase", sse("step", { tool: "x", phase: "middle" })],
  ])("treats %s as unavailable", async (_, chunk) => {
    const { client } = clientAnswering(streamResponse([chunk]));
    expect(await client.send({ message: "Hola", threadId: null })).toEqual({
      ok: false,
      error: { kind: "unavailable" },
    });
  });

  it("turns an error event into the error of its status", async () => {
    const { client } = clientAnswering(
      streamResponse([
        sse("step", { tool: "search_projects", phase: "start" }),
        sse("error", { status: 503, detail: "advisor could not answer" }),
      ]),
    );
    expect(await client.send({ message: "Hola", threadId: null })).toEqual({
      ok: false,
      error: { kind: "unavailable" },
    });
  });

  it("calls a stream that ends before the answer a lost connection", async () => {
    const { client } = clientAnswering(
      streamResponse([sse("step", { tool: "search_projects", phase: "start" })]),
    );
    expect(await client.send({ message: "Hola", threadId: null })).toEqual({
      ok: false,
      error: { kind: "connection" },
    });
  });

  it("calls a stream cut by the network a lost connection", async () => {
    const { client } = clientAnswering(
      streamResponse([sse("step", { tool: "search_projects", phase: "start" })], {
        cutAfter: true,
      }),
    );
    expect(await client.send({ message: "Hola", threadId: null })).toEqual({
      ok: false,
      error: { kind: "connection" },
    });
  });

  it("calls a failed request a lost connection", async () => {
    const { client } = clientAnswering(new TypeError("Failed to fetch"));
    expect(await client.send({ message: "Hola", threadId: null })).toEqual({
      ok: false,
      error: { kind: "connection" },
    });
  });

  it("calls a 200 that is not a stream unavailable", async () => {
    const { client } = clientAnswering(jsonResponse(200, ANSWER));
    expect(await client.send({ message: "Hola", threadId: null })).toEqual({
      ok: false,
      error: { kind: "unavailable" },
    });
  });

  const limited = (seconds: string) =>
    jsonResponse(429, { detail: "too many requests" }, { "retry-after": seconds });

  it.each([
    [limited("20"), { kind: "rate-minute", retryAfterSeconds: 20 }],
    [limited("3600"), { kind: "rate-day", retryAfterSeconds: 3600 }],
    [jsonResponse(503, { detail: BUDGET_DETAIL }), { kind: "budget" }],
    [jsonResponse(503, { detail: "service unavailable" }), { kind: "unavailable" }],
    [jsonResponse(409, { detail: "conversation limit reached" }), { kind: "full" }],
    [jsonResponse(404, { detail: "conversation not found" }), { kind: "gone" }],
    [jsonResponse(422, { detail: [] }), { kind: "unavailable" }],
    [new Response("<html>Bad gateway</html>", { status: 502 }), { kind: "unavailable" }],
  ])("translates an HTTP refusal (%#)", async (response, error) => {
    const { client } = clientAnswering(response);
    expect(await client.send({ message: "Hola", threadId: THREAD })).toEqual({ ok: false, error });
  });

  it("allows one message in flight: a second send meanwhile sends nothing", async () => {
    let release: (() => void) | undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const fetchImpl = vi.fn(async () => {
      await gate;
      return streamResponse([sse("answer", ANSWER)]);
    });
    const client = new AdvisorClient(API, fetchImpl as unknown as typeof fetch);

    const first = client.send({ message: "Hola", threadId: null });
    expect(client.busy).toBe(true);
    expect(await client.send({ message: "Otra", threadId: null })).toEqual({
      ok: false,
      error: { kind: "busy" },
    });
    release?.();
    expect((await first).ok).toBe(true);
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    expect(client.busy).toBe(false);
  });
});

describe("errorFor", () => {
  it("draws the line between the minute and the day at 60 seconds", () => {
    expect(errorFor(429, null, 60)).toEqual({ kind: "rate-minute", retryAfterSeconds: 60 });
    expect(errorFor(429, null, 61)).toEqual({ kind: "rate-day", retryAfterSeconds: 61 });
  });

  it("assumes the short wait when Retry-After is missing", () => {
    expect(errorFor(429, null, null)).toEqual({ kind: "rate-minute", retryAfterSeconds: 60 });
  });

  it("maps statuses of error events like HTTP ones", () => {
    expect(errorFor(404, "conversation not found", null)).toEqual({ kind: "gone" });
    expect(errorFor(409, "conversation limit reached", null)).toEqual({ kind: "full" });
    expect(errorFor(503, BUDGET_DETAIL, null)).toEqual({ kind: "budget" });
    expect(errorFor(503, "advisor unavailable", null)).toEqual({ kind: "unavailable" });
  });
});
