/**
 * Icons of the Estatery kit, read at build time from the private submodule web/kit/.
 *
 * Without the submodule (a fork, or CI without KIT_REPO_TOKEN) each icon falls back to
 * src/assets/icons-fallback/, our own drawings, so the site still builds. The kit's icons are
 * never copied into this public repository (UI8 license).
 */

const KIT = import.meta.glob<string>("/kit/icons/*.svg", {
  query: "?raw",
  import: "default",
  eager: true,
});
const FALLBACK = import.meta.glob<string>("/src/assets/icons-fallback/*.svg", {
  query: "?raw",
  import: "default",
  eager: true,
});

/** The icons the site uses; each one needs a fallback drawing. */
export const ICON_NAMES = [
  "bed-outline",
  "bath-outline",
  "square-meters-outline",
  "search-outline",
  "chevron-left-outline",
  "filter-outline",
  "map-outline",
  "check-circle-outline",
  "chart-outline",
  "dollar-square-outline",
  "message-outline",
  "property-insurance-outline",
  "properties-outline",
  "calendar-outline",
] as const;

export type IconName = (typeof ICON_NAMES)[number];

function byName(modules: Record<string, string>): Map<string, string> {
  return new Map(
    Object.entries(modules).map(([path, svg]) => [path.slice(path.lastIndexOf("/") + 1, -4), svg]),
  );
}

const kitIcons = byName(KIT);
const fallbackIcons = byName(FALLBACK);

/** Whether the kit's icons are available to this build. */
export const kitAvailable = kitIcons.size > 0;

if (!kitAvailable && import.meta.env.PROD) {
  // Loud on purpose: a production build should not ship placeholder icons by accident.
  console.warn("[icons] web/kit is missing: building with the fallback icons");
}

/** Where an icon comes from in this build. */
export function iconSource(name: IconName): "kit" | "fallback" {
  return kitIcons.has(name) ? "kit" : "fallback";
}

export type IconOptions = {
  /** Width and height in px; the kit draws on 24. */
  size?: number | undefined;
  class?: string | undefined;
  /** Accessible name; without it the icon is decorative and hidden from assistive tech. */
  label?: string | undefined;
};

const escapeAttribute = (value: string) =>
  value.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");

/**
 * The icon's SVG markup, sized and labelled, for `set:html` in an Astro component.
 *
 * Throws if the name has neither a kit icon nor a fallback (a missing fallback is a bug).
 */
export function iconSvg(name: IconName, options: IconOptions = {}): string {
  const svg = kitIcons.get(name) ?? fallbackIcons.get(name);
  if (svg === undefined) throw new Error(`icon ${name} has no kit file and no fallback`);
  const { size = 24, label } = options;
  const attributes = [
    `width="${size}"`,
    `height="${size}"`,
    options.class ? `class="${escapeAttribute(options.class)}"` : "",
    label
      ? `role="img" aria-label="${escapeAttribute(label)}"`
      : `aria-hidden="true" focusable="false"`,
  ]
    .filter(Boolean)
    .join(" ");
  return svg
    .trim()
    .replace(/<svg\b([^>]*)>/, (_, rest: string) => {
      const kept = rest.replace(/\s(?:width|height|class|role|aria-[\w-]+)="[^"]*"/g, "");
      return `<svg${kept} ${attributes}>`;
    });
}
