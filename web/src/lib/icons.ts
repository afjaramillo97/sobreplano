/**
 * Icons of the Estatery kit, read at build time from the private submodule web/kit/.
 *
 * Without the submodule (a fork, or CI without KIT_REPO_TOKEN) each icon falls back to
 * src/assets/icons-fallback/, our own drawings, so the site still builds. The kit's icons are
 * never copied into this public repository (UI8 license).
 */

// Only the icons in ICON_NAMES: the search island ships this module to the browser, and the
// kit has 115 icons. Keep the list in step with ICON_NAMES (tests/unit/icons.test.ts).
const KIT = import.meta.glob<string>(
  [
    "/kit/icons/{bed-outline,bath-outline,square-meters-outline,search-outline,chevron-left-outline}.svg",
    "/kit/icons/{filter-outline,map-outline,check-circle-outline,chart-outline,dollar-square-outline}.svg",
    "/kit/icons/{message-outline,property-insurance-outline,properties-outline,calendar-outline}.svg",
    "/kit/icons/{close-outline,chevron-down-outline,add-outline,check-outline,unordered-list-outline}.svg",
    "/kit/icons/{location-marker-outline,sort-outline,send-bold}.svg",
  ],
  { query: "?raw", import: "default", eager: true },
);
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
  "close-outline",
  "chevron-down-outline",
  "add-outline",
  "check-outline",
  "unordered-list-outline",
  "location-marker-outline",
  "sort-outline",
  "send-bold",
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

if (!kitAvailable && import.meta.env.PROD && import.meta.env.SSR) {
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
  className?: string | undefined;
  /** Accessible name; without it the icon is decorative and hidden from assistive tech. */
  label?: string | undefined;
};

/** The root <svg> attributes as React props, plus the markup inside it. */
export type IconParts = { attributes: Record<string, string>; inner: string };

const SVG = /^\s*<svg\b([^>]*)>([\s\S]*)<\/svg>\s*$/;
const ATTRIBUTE = /([\w:-]+)="([^"]*)"/g;
// The file's own size and labels are replaced by the options.
const REPLACED = /^(?:width|height|class|role|aria-[\w-]+)$/;

/**
 * The icon split for a React <svg>: its root attributes (stroke-width becomes strokeWidth),
 * sized and labelled, and its inner markup.
 *
 * Throws if the name has neither a kit icon nor a fallback (a missing fallback is a bug), or
 * if the file is not a single <svg> element.
 */
export function iconParts(name: IconName, options: IconOptions = {}): IconParts {
  const svg = kitIcons.get(name) ?? fallbackIcons.get(name);
  if (svg === undefined) throw new Error(`icon ${name} has no kit file and no fallback`);
  const match = SVG.exec(svg);
  if (!match) throw new Error(`icon ${name} is not a single <svg> element`);
  const [, rootAttributes = "", inner = ""] = match;
  const attributes: Record<string, string> = {};
  for (const [, key = "", value = ""] of rootAttributes.matchAll(ATTRIBUTE)) {
    if (REPLACED.test(key)) continue;
    attributes[key.replace(/[-:]([a-z])/g, (_, letter: string) => letter.toUpperCase())] = value;
  }
  const { size = 24, className, label } = options;
  attributes.width = String(size);
  attributes.height = String(size);
  if (className) attributes.className = className;
  if (label) {
    attributes.role = "img";
    attributes["aria-label"] = label;
  } else {
    attributes["aria-hidden"] = "true";
    attributes.focusable = "false";
  }
  return { attributes, inner: inner.trim() };
}
