import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { buildCss, colorVar, flatten, indexTokens, resolve } from "../../scripts/build-tokens.mjs";
import tree from "../../tokens/sobreplano.tokens.json";

describe("build-tokens", () => {
  it("tokens.css is up to date with the tokens", () => {
    const current = readFileSync(new URL("../../src/styles/tokens.css", import.meta.url), "utf8");
    expect(current).toBe(buildCss(tree));
  });

  it("names colors: primitives without 'primitive', no trailing 'default'", () => {
    expect(colorVar(["color", "primitive", "purple", "500"])).toBe("--color-purple-500");
    expect(colorVar(["color", "action", "default"])).toBe("--color-action");
    expect(colorVar(["color", "border", "input"])).toBe("--color-border-input");
  });

  it("resolves aliases and refuses unknown or circular ones", () => {
    const index = indexTokens(flatten(tree));
    expect(resolve("{color.action.default}", index)).toBe("#685DE8");
    expect(() => resolve("{color.nope}", index)).toThrow(/unknown alias/);
    const loop = indexTokens(flatten({ a: { $value: "{b}" }, b: { $value: "{a}" } }));
    expect(() => resolve("{a}", loop)).toThrow(/circular/);
  });

  it("resets Tailwind's default palette, radii, shadows and fonts", () => {
    const css = buildCss(tree);
    for (const ns of ["color", "radius", "shadow", "font", "font-weight", "text"]) {
      expect(css).toContain(`--${ns}-*: initial;`);
    }
  });

  it("points shadcn variables at semantic tokens", () => {
    const css = buildCss(tree);
    expect(css).toContain("--primary: var(--color-action);");
    expect(css).toContain("--ring: var(--color-focus-ring);");
    expect(css).toContain("--radius: 8px;");
  });
});
