// The steps of a reply while it runs: "Pensando…" until the first tool, then one line per tool,
// running or done. A polite live region, so a screen reader hears each new step without the
// focus leaving the composer. The orbit and the shimmer go on one line only (SPEC 11e).
import Icon from "@/components/Icon";
import { doneLabel, runningLabel, THINKING } from "@/lib/advisor/labels";
import { AdvisorAvatar } from "./Bubble";
import { ShimmerText } from "./ShimmerText";
import { ThinkingOrbit } from "./ThinkingOrbit";

export type StepView = { tool: string; done: boolean };

/** The step that carries the animation: the most recent one still running, or -1. */
export function animatedStep(steps: readonly StepView[]): number {
  return steps.findLastIndex((step) => !step.done);
}

export function StepTrace({ steps }: { steps: readonly StepView[] }) {
  const animated = animatedStep(steps);
  return (
    <div className="flex items-start gap-3 sm:gap-4">
      <AdvisorAvatar />
      <div
        aria-live="polite"
        aria-atomic="false"
        className="flex flex-col gap-2 rounded-md rounded-tl-none border-(length:--border-width-default) border-border-input bg-bg-surface p-4"
        data-testid="step-trace"
      >
        {steps.length === 0 ? (
          <p className="flex items-center gap-2 text-body-sm text-text-secondary">
            <ThinkingOrbit />
            <ShimmerText text={THINKING} />
          </p>
        ) : (
          <ul className="flex flex-col gap-2">
            {steps.map((step, index) => (
              // Steps only ever append, so the index is a stable key.
              <li key={index} className="flex items-center gap-2 text-body-sm text-text-secondary">
                {step.done ? (
                  <span className="flex h-4 w-6 shrink-0 justify-center">
                    <Icon name="check-outline" size={16} className="text-action" />
                  </span>
                ) : index === animated ? (
                  <ThinkingOrbit />
                ) : (
                  <Dot />
                )}
                {step.done ? (
                  doneLabel(step.tool)
                ) : index === animated ? (
                  <ShimmerText text={runningLabel(step.tool)} />
                ) : (
                  runningLabel(step.tool)
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

/**
 * A still dot for a step running behind the newest one, so only one loop runs at a time. As
 * wide as the orbit (24), as tall as before (16): the texts line up and the card grows only on
 * the orbit's line.
 */
function Dot() {
  return (
    <span aria-hidden="true" className="flex h-4 w-6 shrink-0 items-center justify-center">
      <span className="size-2 rounded-full bg-action" />
    </span>
  );
}
