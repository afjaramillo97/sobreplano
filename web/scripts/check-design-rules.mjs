// Fails with file:line when web/src uses a color, radius, shadow or font outside the tokens.
// Rules in web/DESIGN.md. No dependencies. Run: pnpm rules.
//
// Skipped: src/styles/tokens.css (generated from the tokens) and src/components/ui/ (shadcn
// code, reviewed once when added; it uses semantic classes such as bg-primary).

import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";

const WEB = join(dirname(fileURLToPath(import.meta.url)), "..");
const SRC = join(WEB, "src");
const EXTENSIONS = /\.(astro|tsx|ts|css)$/;
const SKIPPED = [join("src", "styles", "tokens.css"), join("src", "components", "ui") + sep];

const PALETTE =
  "slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose";
const RADII = new Set(["sm", "md", "lg", "full", "none"]);
const SHADOWS = new Set(["sm", "float", "none"]);
// Weights from the tokens, and the one family.
const FONT_UTILITIES = new Set(["sans", "regular", "medium", "bold", "extrabold"]);

/** Each rule finds offending text in one line and says why. */
const RULES = [
  {
    pattern: new RegExp(
      `(?<![\\w-])(?:bg|text|border|ring|fill|stroke|from|via|to)-(?:${PALETTE})-\\d{2,3}\\b`,
      "g",
    ),
    message: "Tailwind default palette; use a semantic token (bg-action, text-text-primary, ...)",
  },
  {
    pattern: /#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})\b/g,
    message: "loose hex color; use a token",
  },
  {
    pattern: /\b(?:rgba?|hsla?|oklch|oklab|lab|lch|hwb)\(/g,
    message: "loose color function; use a token",
  },
  {
    pattern:
      /(?<![\w-])rounded-(?:(?:tl|tr|br|bl|ss|se|es|ee|t|r|b|l|s|e|x|y)-)?([\w[\]().:%/-]+)/g,
    check: (match) => !RADII.has(match[1]),
    message: "radius outside the scale (sm, md, lg, full)",
  },
  {
    pattern: /(?<![\w-])shadow-([\w[\]().:%/-]+)/g,
    check: (match) => !SHADOWS.has(match[1]),
    message: "shadow outside the tokens (shadow-sm, shadow-float)",
  },
  {
    // A font-* utility; CSS properties (font-family:, font-weight:, ...) are skipped. The
    // first lookahead makes the class name whole, so "font-family:" cannot match "font-famil";
    // the second skips properties and object keys ("font-weight": ...).
    pattern: /(?<![\w-])font-([\w[\]().%/-]+)(?![\w[\]().%/-])(?!["']?\s*:)/g,
    check: (match) =>
      !FONT_UTILITIES.has(match[1]) && !/^(?:variant|feature|synthesis)/.test(match[1]),
    message: "font utility outside the tokens (font-sans and the token weights)",
  },
  {
    pattern: /font-family\s*:(?!\s*(?:var\(--font-sans\)|inherit))/g,
    message: "font-family must be var(--font-sans)",
  },
  {
    pattern: /\b(?:Inter|Roboto|Poppins|Montserrat|Playfair)\b/g,
    message: "font other than Plus Jakarta Sans",
  },
];

/** Problems in one file's text, as { line, column, text, message }. */
export function checkSource(text) {
  const problems = [];
  text.split("\n").forEach((line, i) => {
    for (const rule of RULES) {
      for (const match of line.matchAll(rule.pattern)) {
        if (rule.check && !rule.check(match)) continue;
        problems.push({ line: i + 1, column: match.index + 1, text: match[0], message: rule.message });
      }
    }
  });
  return problems;
}

/** Files under web/src that the rules apply to, as paths relative to web/. */
export function sourceFiles(dir = SRC) {
  const files = [];
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    const rel = relative(WEB, path);
    if (statSync(path).isDirectory()) {
      if (!SKIPPED.includes(rel + sep)) files.push(...sourceFiles(path));
    } else if (EXTENSIONS.test(name) && !SKIPPED.includes(rel)) {
      files.push(rel);
    }
  }
  return files.sort();
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  let count = 0;
  for (const file of sourceFiles()) {
    for (const p of checkSource(readFileSync(join(WEB, file), "utf8"))) {
      console.error(`${file}:${p.line}:${p.column}  ${p.text}  ${p.message}`);
      count += 1;
    }
  }
  if (count > 0) {
    console.error(`\n${count} design rule violation(s); see web/DESIGN.md`);
    process.exit(1);
  }
  console.log("design rules: ok");
}
