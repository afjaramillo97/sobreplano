// Turns tokens/sobreplano.tokens.json (DTCG) into src/styles/tokens.css. No dependencies.
//
// Output, in three blocks:
// - @theme: primitives and scales, with Tailwind's default palette, radii, shadows and fonts
//   reset, so only token utilities exist.
// - :root: semantic colors (--color-bg-canvas, --color-action, ...) and the variables shadcn
//   reads (--background, --primary, --ring, --radius, ...), pointing at the semantics.
// - @theme inline reference: utilities for those :root variables (bg-action, bg-primary, ...)
//   without redefining them, so dark mode can later override :root alone.
//
// Run: pnpm tokens. CI runs it and fails if tokens.css changes (git diff --exit-code).

import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const WEB = join(dirname(fileURLToPath(import.meta.url)), "..");
const SOURCE = join(WEB, "tokens", "sobreplano.tokens.json");
const TARGET = join(WEB, "src", "styles", "tokens.css");

/** Walk a DTCG tree and return its tokens as { path, type, value, description }. */
export function flatten(tree) {
  const tokens = [];
  const walk = (node, path, inheritedType) => {
    const type = node.$type ?? inheritedType;
    if ("$value" in node) {
      tokens.push({ path, type, value: node.$value, description: node.$description });
      return;
    }
    for (const [key, child] of Object.entries(node)) {
      if (key.startsWith("$")) continue;
      walk(child, [...path, key], type);
    }
  };
  walk(tree, [], undefined);
  return tokens;
}

/** Index tokens by dotted path, for alias resolution. */
export function indexTokens(tokens) {
  return new Map(tokens.map((token) => [token.path.join("."), token]));
}

const ALIAS = /^\{([^}]+)\}$/;

/** Follow {a.b.c} aliases until a concrete value; throws on an unknown or circular alias. */
export function resolve(value, index, seen = new Set()) {
  if (typeof value !== "string") return value;
  const match = ALIAS.exec(value);
  if (!match) return value;
  const target = match[1];
  if (seen.has(target)) throw new Error(`circular alias ${target}`);
  const token = index.get(target);
  if (!token) throw new Error(`unknown alias ${value}`);
  return resolve(token.value, index, new Set([...seen, target]));
}

/** The dotted path an alias points to, or null if the value is not an alias. */
function aliasTarget(value) {
  const match = typeof value === "string" ? ALIAS.exec(value) : null;
  return match ? match[1] : null;
}

const dimension = (v) => `${v.value}${v.unit}`;

/** CSS name of a color token: primitives drop "primitive", a trailing "default" is dropped. */
export function colorVar(path) {
  const parts = path.slice(1).filter((part, i) => !(i === 0 && part === "primitive"));
  if (parts.length > 1 && parts.at(-1) === "default") parts.pop();
  return `--color-${parts.join("-")}`;
}

const isPrimitive = (path) => path[0] === "color" && path[1] === "primitive";

function fontFamily(names) {
  return names.map((name) => (/[\s]/.test(name) ? `"${name}"` : name)).join(", ");
}

function shadow(v) {
  return [v.offsetX, v.offsetY, v.blur, v.spread].map(dimension).join(" ") + ` ${v.color}`;
}

// shadcn/ui variable → semantic token it shows. Components use bg-primary, text-foreground, ...
const SHADCN = {
  background: "color.bg.canvas",
  foreground: "color.text.primary",
  card: "color.bg.surface",
  "card-foreground": "color.text.primary",
  popover: "color.bg.surface",
  "popover-foreground": "color.text.primary",
  primary: "color.action.default",
  "primary-foreground": "color.text.on-action",
  secondary: "color.action.soft",
  "secondary-foreground": "color.action.soft-text",
  muted: "color.bg.subtle",
  "muted-foreground": "color.text.muted",
  accent: "color.bg.selected",
  "accent-foreground": "color.text.primary",
  destructive: "color.text.danger",
  border: "color.border.default",
  input: "color.border.input",
  ring: "color.focus.ring",
  "chart-1": "color.action.default",
  "chart-2": "color.action.dark",
};

/** Build the text of tokens.css from the DTCG tree. Pure, so tests can call it. */
export function buildCss(tree) {
  const tokens = flatten(tree);
  const index = indexTokens(tokens);
  const byGroup = (group) => tokens.filter((t) => t.path[0] === group);
  const theme = [];
  const root = [];
  const utilities = [];

  // Reset Tailwind's defaults: utilities outside the tokens must not exist at all.
  for (const ns of [
    "color",
    "font",
    "font-weight",
    "text",
    "radius",
    "shadow",
    "inset-shadow",
    "drop-shadow",
    "text-shadow",
    "ease",
  ]) {
    theme.push(`--${ns}-*: initial;`);
  }

  // Spacing: Tailwind multiplies one base, so the scale must be quarter steps of space.1.
  const base = resolve(index.get("space.1")?.value, index);
  if (!base) throw new Error("space.1 is required: it is Tailwind's spacing base");
  for (const token of byGroup("space")) {
    const steps = token.value.value / base.value;
    if (token.value.unit !== base.unit || !Number.isInteger(steps * 4)) {
      throw new Error(`space.${token.path[1]} is not a quarter step of space.1`);
    }
  }
  theme.push(`--spacing: ${dimension(base)};`);

  const themeNames = new Map(); // css name → token path, to catch collisions
  const themeVar = (name, value, path) => {
    if (themeNames.has(name)) throw new Error(`${name} defined twice`);
    themeNames.set(name, path);
    theme.push(`${name}: ${value};`);
  };

  // Primitive colors.
  for (const token of byGroup("color").filter((t) => isPrimitive(t.path))) {
    themeVar(colorVar(token.path), resolve(token.value, index), token.path.join("."));
  }

  // Fonts.
  for (const token of byGroup("font")) {
    const [, kind, name] = token.path;
    const value = resolve(token.value, index);
    if (kind === "family") themeVar(`--font-${name}`, fontFamily(value), token.path.join("."));
    if (kind === "weight") themeVar(`--font-weight-${name}`, value, token.path.join("."));
    if (kind === "size") themeVar(`--text-${name}`, dimension(value), token.path.join("."));
  }

  // Typography: one Tailwind text-* utility per style (size, line height, tracking, weight).
  for (const token of byGroup("typography")) {
    const name = token.path[1];
    const v = token.value;
    if (aliasTarget(v.fontFamily) !== "font.family.sans") {
      throw new Error(`typography.${name} must use font.family.sans: there is one family`);
    }
    themeVar(`--text-${name}`, dimension(resolve(v.fontSize, index)), token.path.join("."));
    theme.push(`--text-${name}--line-height: ${v.lineHeight};`);
    theme.push(`--text-${name}--letter-spacing: ${dimension(v.letterSpacing)};`);
    theme.push(`--text-${name}--font-weight: ${resolve(v.fontWeight, index)};`);
  }

  for (const token of byGroup("radius")) {
    themeVar(`--radius-${token.path[1]}`, dimension(token.value), token.path.join("."));
  }
  for (const token of byGroup("border-width")) {
    themeVar(`--border-width-${token.path[1]}`, dimension(token.value), token.path.join("."));
  }
  for (const token of byGroup("shadow")) {
    themeVar(`--shadow-${token.path[1]}`, shadow(token.value), token.path.join("."));
  }
  for (const token of byGroup("size")) {
    themeVar(`--size-${token.path[1]}`, dimension(token.value), token.path.join("."));
  }
  for (const token of byGroup("duration")) {
    themeVar(`--duration-${token.path[1]}`, dimension(token.value), token.path.join("."));
  }
  for (const token of byGroup("easing")) {
    themeVar(
      `--ease-${token.path[1]}`,
      `cubic-bezier(${token.value.join(", ")})`,
      token.path.join("."),
    );
  }

  // Semantic colors, as aliases of primitive variables.
  const semanticNames = new Map(); // css name → token path
  for (const token of byGroup("color").filter((t) => !isPrimitive(t.path))) {
    const name = colorVar(token.path);
    const target = aliasTarget(token.value);
    if (!target || !isPrimitive(target.split("."))) {
      throw new Error(`${token.path.join(".")} must alias a primitive color`);
    }
    const value = `var(${colorVar(target.split("."))})`;
    semanticNames.set(name, token.path.join("."));
    if (themeNames.has(name)) {
      // color.map.land and color.primitive.map.land share a name; fine only if equal.
      if (themeNames.get(name) !== target) throw new Error(`${name} collides with a primitive`);
      continue;
    }
    root.push(`${name}: ${value};`);
    utilities.push(`${name}: var(${name});`);
  }

  // shadcn/ui variables and their utilities (bg-primary, ring-ring, ...).
  root.push(`--radius: ${dimension(resolve(index.get("radius.md")?.value, index))};`);
  for (const [name, path] of Object.entries(SHADCN)) {
    if (!index.has(path)) throw new Error(`shadcn --${name} points to unknown ${path}`);
    const semantic = colorVar(path.split("."));
    root.push(`--${name}: var(${semantic});`);
    const utility = `--color-${name}`;
    if (semanticNames.has(utility)) {
      // --color-border is both color.border.default and shadcn's border: same token or fail.
      if (semanticNames.get(utility) !== path) throw new Error(`${utility} means two things`);
      continue;
    }
    utilities.push(`${utility}: var(--${name});`);
  }

  const block = (header, lines) => `${header} {\n${lines.map((l) => `  ${l}`).join("\n")}\n}\n`;
  return [
    "/* Generated by web/scripts/build-tokens.mjs from web/tokens/sobreplano.tokens.json.",
    "   Do not edit: change the tokens and run pnpm tokens. */\n",
    block("@theme", theme),
    block(":root", root),
    block("@theme inline reference", utilities),
  ].join("\n");
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const tree = JSON.parse(readFileSync(SOURCE, "utf8"));
  writeFileSync(TARGET, buildCss(tree));
  console.log(`wrote ${TARGET}`);
}
