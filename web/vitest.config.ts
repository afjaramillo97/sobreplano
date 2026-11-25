/// <reference types="vitest/config" />
import { getViteConfig } from "astro/config";

// Astro's Vite config, so import.meta.glob and aliases behave as in the build.
export default getViteConfig({
  test: {
    include: ["tests/unit/**/*.test.ts"],
  },
});
