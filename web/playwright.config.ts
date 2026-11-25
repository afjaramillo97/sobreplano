import { defineConfig, devices } from "@playwright/test";

// Browser tests against the built site (pnpm build first). The API with the fictitious
// catalog must be running at PUBLIC_API_URL, with CORS open to this origin (SPEC 11a §10).
// E2E_PORT moves the preview when 4321 is taken (by a dev server, say).
const port = Number(process.env.E2E_PORT ?? 4321);

export default defineConfig({
  testDir: "tests/e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  // One file per capture, without the platform: the captures are made on Linux only, with the
  // official Playwright image, because fonts render differently on every system.
  snapshotPathTemplate: "{testDir}/{testFileName}-snapshots/{arg}{ext}",
  expect: { toHaveScreenshot: { maxDiffPixelRatio: 0.01, animations: "disabled" } },
  use: {
    baseURL: `http://localhost:${port}`,
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    // Straight from node_modules: the Playwright image that runs the captures has no pnpm.
    // --ignore-lock: a preview left running in the background must not stop the test server.
    command: `node_modules/.bin/astro preview --port ${port} --ignore-lock`,
    url: `http://localhost:${port}/`,
    reuseExistingServer: !process.env.CI,
  },
});
