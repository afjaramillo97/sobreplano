import { afterEach, describe, expect, it, vi } from "vitest";
import { browserApiClient, buildApiClient, createApiClient } from "../../src/lib/api/client";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

/** Replaces fetch with one that records each request and answers `body`. */
function fakeFetch(body: unknown, status = 200) {
  const requests: Request[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      requests.push(request);
      return new Response(JSON.stringify(body), {
        status,
        headers: { "content-type": "application/json" },
      });
    }),
  );
  return requests;
}

describe("api client", () => {
  it("sends typed query parameters to the base URL, without a double slash", async () => {
    const requests = fakeFetch({ items: [], total: 0, limit: 50, offset: 100 });
    const api = createApiClient("http://localhost:8000/");
    const { data } = await api.GET("/projects", { params: { query: { limit: 50, offset: 100 } } });
    expect(requests[0]?.url).toBe("http://localhost:8000/projects?limit=50&offset=100");
    expect(data?.total).toBe(0);
  });

  it("puts the slug in the path and hands back errors with their response", async () => {
    const requests = fakeFetch({ detail: "too many requests" }, 429);
    const api = createApiClient("http://localhost:8000");
    const { data, error, response } = await api.GET("/projects/{slug}", {
      params: { path: { slug: "torre-ejemplo" } },
    });
    expect(requests[0]?.url).toBe("http://localhost:8000/projects/torre-ejemplo");
    expect(data).toBeUndefined();
    expect(error).toEqual({ detail: "too many requests" });
    expect(response.status).toBe(429);
  });

  it("refuses to build or browse without its URL", () => {
    vi.stubEnv("SOBREPLANO_API_URL", "");
    vi.stubEnv("PUBLIC_API_URL", "");
    expect(() => buildApiClient()).toThrow(/SOBREPLANO_API_URL/);
    expect(() => browserApiClient()).toThrow(/PUBLIC_API_URL/);
  });
});
