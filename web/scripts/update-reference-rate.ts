// Rewrites src/data/reference-rate.json with the latest week of the Superfinanciera's open data,
// to refresh the versioned fallback in a PR (SPEC 11d §3). Exits 1, leaving the file as it was,
// if the answer cannot be used.
//
// Run: pnpm rate:update (Node runs the TypeScript as it is).

import { writeFileSync } from "node:fs";

import { fetchReferenceRate } from "../src/lib/reference-rate.ts";

const TARGET = new URL("../src/data/reference-rate.json", import.meta.url);

try {
  const rate = await fetchReferenceRate();
  const text = `${JSON.stringify(rate, null, 2)}\n`;
  writeFileSync(TARGET, text);
  process.stdout.write(`wrote src/data/reference-rate.json\n${text}`);
} catch (error) {
  console.error(`rate:update failed: ${error instanceof Error ? error.message : String(error)}`);
  process.exitCode = 1;
}
