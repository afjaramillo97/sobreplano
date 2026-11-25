/**
 * Which links of an advisor answer stay links (SPEC 11c): project pages of this site and https
 * pages of the developers in the catalog. Anything else stays as text.
 *
 * An answer is untrusted input: a scraped page could have slipped a link into what the model
 * says (docs/security.md, prompt injection), so the allow list comes from the catalog of the
 * build, never from the answer.
 */

/** A link that may be rendered, and whether it leaves the site. */
export type SafeLink = { href: string; external: boolean };

/** Decides, for one href of an answer, the link to render or null for plain text. */
export type LinkPolicy = (href: string) => SafeLink | null;

const PROJECT_PATH = /^\/proyectos\/[a-z0-9]+(?:-[a-z0-9]+)*\/?$/;
// Any origin works as the base: it only resolves relative paths, and a path that escapes it
// (//host, /\host) ends with another origin and is refused.
const BASE = "https://sobreplano.invalid";

/** The host without a leading "www.", lower case, so both spellings of a domain match. */
function bareHost(hostname: string): string {
  return hostname.toLowerCase().replace(/^www\./, "");
}

/** The hosts of the catalog's https source URLs; other schemes and bad URLs are skipped. */
export function allowedHostsFrom(sourceUrls: readonly string[]): string[] {
  const hosts = new Set<string>();
  for (const url of sourceUrls) {
    try {
      const parsed = new URL(url);
      if (parsed.protocol === "https:") hosts.add(bareHost(parsed.hostname));
    } catch {
      // A catalog URL that does not parse adds no host.
    }
  }
  return [...hosts].sort();
}

/**
 * The policy for these developer hosts: /proyectos/{slug}/ inside the site, and https URLs on
 * those hosts, without credentials or a port. Everything else, javascript: and data: included,
 * is refused.
 */
export function linkPolicy(allowedHosts: readonly string[]): LinkPolicy {
  const hosts = new Set(allowedHosts.map(bareHost));
  return (href) => {
    const trimmed = href.trim();
    if (trimmed.startsWith("/")) return projectLink(trimmed);
    let url: URL;
    try {
      url = new URL(trimmed);
    } catch {
      return null;
    }
    if (url.protocol !== "https:" || url.username || url.password || url.port) return null;
    if (!hosts.has(bareHost(url.hostname))) return null;
    return { href: url.href, external: true };
  };
}

function projectLink(path: string): SafeLink | null {
  let url: URL;
  try {
    url = new URL(path, BASE);
  } catch {
    return null;
  }
  if (url.origin !== BASE || !PROJECT_PATH.test(url.pathname)) return null;
  const pathname = url.pathname.endsWith("/") ? url.pathname : `${url.pathname}/`;
  return { href: pathname, external: false };
}
