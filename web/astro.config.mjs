// @ts-check
import react from "@astrojs/react";
import sitemap from "@astrojs/sitemap";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "astro/config";

// The site's public address, for canonical URLs, og:image and the sitemap. The domain comes
// with the deployment (SPEC 12); until then the local preview.
const site = process.env.PUBLIC_SITE_URL ?? "http://localhost:4321";

// The browser asks the API for the price history only; the CSP lets it reach that origin and,
// for the search map (SPEC 11b), OpenFreeMap's style, tiles, fonts and sprites.
const apiOrigin = process.env.PUBLIC_API_URL ? new URL(process.env.PUBLIC_API_URL).origin : null;
const mapOrigin = "https://tiles.openfreemap.org";

// Static output only: the site is HTML built from the API, plus one island (SPEC 11a).
export default defineConfig({
  site,
  output: "static",
  trailingSlash: "always",
  integrations: [react(), sitemap({ filter: (page) => !page.includes("/404") })],
  vite: {
    plugins: [tailwindcss()],
  },
  // Astro hashes its own scripts and styles and writes the policy in a <meta> on every page.
  // A <meta> policy cannot carry frame-ancestors or reporting: those come as headers in SPEC 12.
  security: {
    csp: {
      directives: [
        "default-src 'self'",
        // blob: for the map's sprites and glyphs, which MapLibre decodes from blobs.
        "img-src 'self' data: blob:",
        "font-src 'self'",
        `connect-src 'self'${apiOrigin ? ` ${apiOrigin}` : ""} ${mapOrigin}`,
        // MapLibre's worker, served from the site (setWorkerUrl), never from a blob: URL.
        "worker-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
      ],
    },
  },
});
