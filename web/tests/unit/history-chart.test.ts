import { describe, expect, it } from "vitest";
import { ApiError, shouldRetry } from "../../src/components/HistoryChart";

describe("history query retries", () => {
  it("never retries a 429 or a 404: each request counts against the reader's limit", () => {
    expect(shouldRetry(0, new ApiError(429, 120))).toBe(false);
    expect(shouldRetry(0, new ApiError(404, null))).toBe(false);
  });

  it("retries a server error or a network failure once", () => {
    expect(shouldRetry(0, new ApiError(503, null))).toBe(true);
    expect(shouldRetry(0, new TypeError("Failed to fetch"))).toBe(true);
    expect(shouldRetry(1, new ApiError(503, null))).toBe(false);
    expect(shouldRetry(1, new TypeError("Failed to fetch"))).toBe(false);
  });
});
