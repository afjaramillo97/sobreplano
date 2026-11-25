import { describe, expect, it } from "vitest";
import { checkSource, sourceFiles } from "../../scripts/check-design-rules.mjs";

const texts = (source: string) => checkSource(source).map((p: { text: string }) => p.text);

describe("design rules", () => {
  it("rejects Tailwind's default palette", () => {
    expect(texts('<div class="bg-indigo-600 hover:text-slate-500">')).toEqual([
      "bg-indigo-600",
      "text-slate-500",
    ]);
  });

  it("rejects loose colors", () => {
    expect(texts("color: #7065F0;")).toEqual(["#7065F0"]);
    expect(texts("color: #fff; fill: rgba(0, 0, 0, .5); x: oklch(0.6 0.2 280)")).toEqual([
      "#fff",
      "rgba(",
      "oklch(",
    ]);
  });

  it("reports file positions as line and column", () => {
    expect(checkSource('---\n---\n<p class="p-4 bg-indigo-600">')).toEqual([
      expect.objectContaining({ line: 3, column: 15, text: "bg-indigo-600" }),
    ]);
  });

  it("accepts the token scale for radii and shadows", () => {
    expect(texts('class="rounded-lg rounded-t-md rounded-full shadow-sm shadow-float"')).toEqual([]);
    expect(texts('class="rounded-xl rounded-tl-2xl shadow-lg shadow-[0_0_4px]"')).toEqual([
      "rounded-xl",
      "rounded-tl-2xl",
      "shadow-lg",
      "shadow-[0_0_4px]",
    ]);
  });

  it("accepts token weights and the one family, not others", () => {
    expect(texts('class="font-sans font-extrabold font-medium"')).toEqual([]);
    expect(texts('class="font-semibold font-serif"')).toEqual(["font-semibold", "font-serif"]);
    expect(texts("font-family: var(--font-sans); font-weight: 700;")).toEqual([]);
    expect(texts("font-family: Georgia;")).toEqual(["font-family:"]);
    expect(texts('const f = "Inter";')).toEqual(["Inter"]);
    expect(texts('theme: { "font-weight": WEIGHTS }')).toEqual([]); // an object key
  });

  it("leaves semantic classes, CSS variables and anchors alone", () => {
    const source = [
      '<a href="#contenido" class="bg-action text-text-price border-border-input">',
      "box-shadow: var(--shadow-float); border-radius: var(--radius-lg);",
      '<div class="text-primary-foreground ring-ring rounded-md">',
    ].join("\n");
    expect(texts(source)).toEqual([]);
  });

  it("skips the generated tokens and shadcn's components", () => {
    const files = sourceFiles();
    expect(files).not.toContain("src/styles/tokens.css");
    expect(files.some((f: string) => f.startsWith("src/components/ui/"))).toBe(false);
  });
});
