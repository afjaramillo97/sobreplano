// The site's robots.txt: everything may be indexed, and the sitemap says what there is. (The
// API's own robots.txt disallows everything; the terms of use forbid bulk copying.)
import type { APIRoute } from "astro";

export const GET: APIRoute = ({ site }) => {
  const sitemap = new URL("sitemap-index.xml", site);
  return new Response(`User-agent: *\nAllow: /\n\nSitemap: ${sitemap.href}\n`, {
    headers: { "Content-Type": "text/plain; charset=utf-8" },
  });
};
