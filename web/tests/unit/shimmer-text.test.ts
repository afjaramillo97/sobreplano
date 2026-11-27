import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import {
  applyShimmerDelays,
  LETTER_DELAY_MS,
  ShimmerText,
  shimmerWords,
} from "../../src/components/advisor/ShimmerText";

const render = (text: string) => renderToStaticMarkup(createElement(ShimmerText, { text }));

describe("ShimmerText", () => {
  it("keeps the whole text once, in the sr-only span", () => {
    const html = render("Buscando proyectos…");
    expect(html).toContain('<span class="sr-only">Buscando proyectos…</span>');
    // The letters are drawn from data-char, so the text appears nowhere else.
    expect(html.split("Buscando").length - 1).toBe(1);
  });

  it("puts each letter in a hidden span, 60 ms after the one before it", () => {
    const html = render("Pensando…");
    const letters = [...html.matchAll(/<span aria-hidden="true" data-char="([^"]*)"/g)].map(
      (m) => m[1],
    );
    expect(letters).toEqual([..."Pensando…"]);
    expect(html).toMatch(/^<span[^>]*><span class="sr-only">Pensando…<\/span><span aria-hidden="true">/);

    expect(shimmerWords("Pensando…")[0]?.map((l) => l.delayMs)).toEqual(
      Array.from({ length: 9 }, (_, i) => i * 60),
    );
    const styled = Array.from({ length: 4 }, () => ({ style: { animationDelay: "" } }));
    applyShimmerDelays(styled);
    expect(styled.map((s) => s.style.animationDelay)).toEqual(["0ms", "60ms", "120ms", "180ms"]);
    expect(LETTER_DELAY_MS).toBe(60);
  });

  it("groups the letters by word, so a line breaks only between words", () => {
    const html = render("Calculando la cuota inicial…");
    const words = [...html.matchAll(/<span class="whitespace-nowrap">(.*?)<\/span>(?= |<\/span><\/span>$)/g)];
    expect(words).toHaveLength(4);
    expect(words.map((w) => [...(w[1] ?? "").matchAll(/data-char="([^"]*)"/g)].map((m) => m[1]).join(""))).toEqual([
      "Calculando",
      "la",
      "cuota",
      "inicial…",
    ]);
  });

  it("counts letters only, so the wave crosses a space without a pause", () => {
    const words = shimmerWords("Revisando constructoras…");
    expect(words.map((w) => w.length)).toEqual([9, 14]);
    expect(words[1]?.[0]?.delayMs).toBe(9 * 60);
  });
});
