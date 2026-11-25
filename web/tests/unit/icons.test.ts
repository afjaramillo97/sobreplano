import { readdirSync, readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { ICON_NAMES, iconSource, iconSvg, kitAvailable } from "../../src/lib/icons";

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
    const svg = iconSvg("bed-outline", { size: 20, class: "shrink-0" });
    expect(svg).toMatch(/^<svg\b/);
    expect(svg).toContain('width="20" height="20"');
    expect(svg).toContain('class="shrink-0"');
    expect(svg).toContain('aria-hidden="true"');
    expect(svg.match(/\swidth="/g)).toHaveLength(1); // the file's own size is replaced
  });

  it("names an icon that carries meaning", () => {
    const svg = iconSvg("check-circle-outline", { label: "Vigente" });
    expect(svg).toContain('role="img" aria-label="Vigente"');
    expect(svg).not.toContain("aria-hidden");
  });
});
