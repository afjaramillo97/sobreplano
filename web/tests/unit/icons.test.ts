import { readdirSync, readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { ICON_NAMES, iconParts, iconSource, kitAvailable } from "../../src/lib/icons";

const FALLBACK_DIR = new URL("../../src/assets/icons-fallback/", import.meta.url);

describe("icons", () => {
  it("has a fallback drawing for every icon the site uses, and nothing else", () => {
    const files = readdirSync(FALLBACK_DIR).map((f) => f.replace(/\.svg$/, ""));
    expect(files.sort()).toEqual([...ICON_NAMES].sort());
  });

  it("draws the fallbacks in currentColor on a 24 px grid", () => {
    for (const name of ICON_NAMES) {
      const svg = readFileSync(new URL(`${name}.svg`, FALLBACK_DIR), "utf8");
      expect(svg).toContain('viewBox="0 0 24 24"');
      expect(svg).toContain("currentColor");
      expect(svg).not.toMatch(/#[0-9a-f]{3,8}\b/i);
    }
  });

  it.runIf(kitAvailable)("takes every icon from the kit when the submodule is there", () => {
    for (const name of ICON_NAMES) expect(iconSource(name)).toBe("kit");
  });

  it("hides decorative icons and sizes them", () => {
    const { attributes, inner } = iconParts("bed-outline", { size: 20, className: "shrink-0" });
    expect(attributes).toMatchObject({
      width: "20",
      height: "20",
      viewBox: "0 0 24 24",
      className: "shrink-0",
      "aria-hidden": "true",
      focusable: "false",
    });
    expect(attributes).not.toHaveProperty("class");
    expect(inner).not.toMatch(/<svg\b/);
    expect(inner).toContain("currentColor");
  });

  it("names an icon that carries meaning", () => {
    const { attributes } = iconParts("check-circle-outline", { label: "Vigente" });
    expect(attributes).toMatchObject({ role: "img", "aria-label": "Vigente" });
    expect(attributes).not.toHaveProperty("aria-hidden");
  });

  it("turns the root's SVG attributes into React props", () => {
    for (const name of ICON_NAMES) {
      for (const key of Object.keys(iconParts(name).attributes)) {
        expect(key, `${name}: ${key}`).toMatch(/^(?:[a-zA-Z]+|aria-hidden|aria-label)$/);
      }
    }
  });
});
