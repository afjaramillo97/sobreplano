/**
 * Typed clients of the Sobreplano API, from the contract in openapi.json (pnpm api:types).
 *
 * Two of them: the build reads the catalog from SOBREPLANO_API_URL; the browser reads only a
 * project's price history, from PUBLIC_API_URL. The history never goes into the static site
 * (SPEC 11a, the detail route has its own rate limit).
 */
import createClient from "openapi-fetch";

import type { components, paths } from "./schema";

export type ApiClient = ReturnType<typeof createClient<paths>>;
export type ProjectOut = components["schemas"]["ProjectOut"];
export type ProjectDetailOut = components["schemas"]["ProjectDetailOut"];
export type UnitTypeOut = components["schemas"]["UnitTypeOut"];
export type PricePointOut = components["schemas"]["PricePointOut"];
export type Municipality = components["schemas"]["Municipality"];

/** A client for the API at `baseUrl`, without a trailing slash. */
export function createApiClient(baseUrl: string): ApiClient {
  return createClient<paths>({ baseUrl: baseUrl.replace(/\/+$/, "") });
}

/**
 * The client of the build. Throws when SOBREPLANO_API_URL is unset: a site built without
 * data would publish an empty catalog.
 */
export function buildApiClient(): ApiClient {
  const url = import.meta.env.SOBREPLANO_API_URL;
  if (!url) throw new Error("SOBREPLANO_API_URL is not set: the build reads the catalog from it");
  return createApiClient(url);
}

/** The client of the browser, for the history island. Throws when PUBLIC_API_URL is unset. */
export function browserApiClient(): ApiClient {
  const url = import.meta.env.PUBLIC_API_URL;
  if (!url) throw new Error("PUBLIC_API_URL is not set: the history chart reads from it");
  return createApiClient(url);
}
