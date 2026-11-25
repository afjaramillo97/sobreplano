import { describe, expect, it } from "vitest";
import { cn, FONT_WEIGHTS, RADII, SHADOWS, TEXT_SIZES } from "../../src/lib/utils";
import tree from "../../tokens/sobreplano.tokens.json";

const keys = (group: object) => Object.keys(group).filter((k) => !k.startsWith("$"));

describe("cn", () => {
  it("lists the same scales as the tokens", () => {
    expect(TEXT_SIZES.sort()).toEqual([...keys(tree.font.size), ...keys(tree.typography)].sort());
    expect(FONT_WEIGHTS.sort()).toEqual(keys(tree.font.weight).sort());
    expect(SHADOWS.sort()).toEqual(keys(tree.shadow).sort());
    expect(RADII.sort()).toEqual(keys(tree.radius).sort());
  });

  it("keeps a text style and a text color together", () => {
    expect(cn("text-price-lg", "text-text-price")).toBe("text-price-lg text-text-price");
  });

  it("lets the last token of a scale win", () => {
    expect(cn("text-h1", "text-h2")).toBe("text-h2");
    expect(cn("shadow-sm", "shadow-float")).toBe("shadow-float");
    expect(cn("font-regular", "font-extrabold")).toBe("font-extrabold");
    expect(cn("rounded-md", "rounded-lg")).toBe("rounded-lg");
    expect(cn("bg-action", "bg-action-dark")).toBe("bg-action-dark");
  });
});
