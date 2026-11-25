import { describe, expect, it } from "vitest";
import { flatten, indexTokens, resolve } from "../../scripts/build-tokens.mjs";
import pairs from "../../tokens/contrast-pairs.json";
import tree from "../../tokens/sobreplano.tokens.json";

const MINIMUM = { text: 4.5, "large-text": 3, "non-text": 3, focus: 3 } as const;
type Kind = keyof typeof MINIMUM;

/** Relative luminance of a #RRGGBB color, as WCAG 2.2 defines it. */
function luminance(hex: string): number {
  const match = /^#([0-9a-f]{6})$/i.exec(hex);
  if (!match?.[1]) throw new Error(`not an opaque #RRGGBB color: ${hex}`);
  const channels = [0, 2, 4].map((i) => Number.parseInt(match[1]!.slice(i, i + 2), 16) / 255);
  const [r, g, b] = channels.map((c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r! + 0.7152 * g! + 0.0722 * b!;
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi! + 0.05) / (lo! + 0.05);
}

const index = indexTokens(flatten(tree));
const color = (path: string): string => {
  if (!index.has(path)) throw new Error(`unknown token ${path}`);
  return resolve(`{${path}}`, index) as string;
};

describe("contrast", () => {
  it("knows the WCAG reference values", () => {
    expect(contrast("#000000", "#FFFFFF")).toBeCloseTo(21, 5);
    expect(contrast("#777777", "#FFFFFF")).toBeCloseTo(4.48, 2);
  });

  it.each(pairs.pairs)("$fg on $bg meets AA ($kind)", ({ fg, bg, kind }) => {
    const ratio = contrast(color(fg), color(bg));
    expect(ratio).toBeGreaterThanOrEqual(MINIMUM[kind as Kind]);
  });

  it("covers the pairs the spec requires", () => {
    const declared = new Set(pairs.pairs.map(({ fg, bg }) => `${fg} on ${bg}`));
    const required = [
      ...["primary", "secondary", "muted"].flatMap((t) =>
        ["canvas", "subtle", "selected"].map((b) => `color.text.${t} on color.bg.${b}`),
      ),
      "color.text.price on color.bg.canvas",
      ...["default", "hover", "dark"].map((a) => `color.text.on-action on color.action.${a}`),
      "color.action.soft-text on color.action.soft",
      "color.change.text on color.change.bg",
      ...["start", "mid", "end"].map(
        (s) => `color.headline-gradient.${s} on color.primitive.hero.top`,
      ),
      "color.focus.ring on color.bg.canvas",
    ];
    for (const pair of required) expect(declared).toContain(pair);
  });

  it("only uses known kinds", () => {
    for (const { kind } of pairs.pairs) expect(Object.keys(MINIMUM)).toContain(kind);
  });
});
