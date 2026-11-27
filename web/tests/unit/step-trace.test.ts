import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { animatedStep, StepTrace, type StepView } from "../../src/components/advisor/StepTrace";

const render = (steps: StepView[]) => renderToStaticMarkup(createElement(StepTrace, { steps }));
const count = (html: string, testId: string) => html.split(`data-testid="${testId}"`).length - 1;

describe("StepTrace", () => {
  it("animates Pensando… before the first step", () => {
    const html = render([]);
    expect(count(html, "thinking-orbit")).toBe(1);
    expect(count(html, "shimmer-text")).toBe(1);
    expect(html).toContain('<span class="sr-only">Pensando…</span>');
  });

  it("with several steps running, animates only the newest, on one line", () => {
    const steps = [
      { tool: "search_projects", done: true },
      { tool: "get_project", done: false },
      { tool: "compare_projects", done: false },
      { tool: "simulate_mortgage", done: true },
    ];
    expect(animatedStep(steps)).toBe(2);
    const html = render(steps);
    expect(count(html, "thinking-orbit")).toBe(1);
    expect(count(html, "shimmer-text")).toBe(1);
    const lines = html.split("<li").slice(1);
    const animated = lines.filter((line) => line.includes("thinking-orbit"));
    expect(animated).toHaveLength(1);
    expect(animated[0]).toContain("shimmer-text");
    expect(animated[0]).toContain("Comparando proyectos…");
    // The done steps are still, with their check and text.
    expect(lines[0]).toContain("Buscó proyectos");
    expect(lines[0]).not.toContain("data-char");
  });

  it("with every step done, nothing moves", () => {
    const html = render([{ tool: "search_projects", done: true }]);
    expect(count(html, "thinking-orbit")).toBe(0);
    expect(count(html, "shimmer-text")).toBe(0);
  });
});
