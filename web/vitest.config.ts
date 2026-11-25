/// <reference types="vitest/config" />
import { getViteConfig } from "astro/config";

// Astro's Vite config, so import.meta.glob and aliases behave as in the build.
export default getViteConfig({
  test: {
    include: ["tests/unit/**/*.test.ts"],
    // West of UTC, where a date formatted in local time would slip to the day before.
    env: { TZ: "America/Bogota" },
  },
});
