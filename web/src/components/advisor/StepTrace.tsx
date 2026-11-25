// The steps of a reply while it runs: "Pensando…" until the first tool, then one line per tool,
// running or done. A polite live region, so a screen reader hears each new step without the
// focus leaving the composer.
import Icon from "@/components/Icon";
import { doneLabel, runningLabel, THINKING } from "@/lib/advisor/labels";
import { AdvisorAvatar } from "./Bubble";

export type StepView = { tool: string; done: boolean };

export function StepTrace({ steps }: { steps: readonly StepView[] }) {
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
            <Dot />
            {THINKING}
          </p>
        ) : (
          <ul className="flex flex-col gap-2">
            {steps.map((step, index) => (
              // Steps only ever append, so the index is a stable key.
              <li key={index} className="flex items-center gap-2 text-body-sm text-text-secondary">
                {step.done ? (
                  <Icon name="check-outline" size={16} className="text-action" />
                ) : (
                  <Dot />
                )}
                {step.done ? doneLabel(step.tool) : runningLabel(step.tool)}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

/** A still dot for "running": no spinner, so nothing moves under prefers-reduced-motion. */
function Dot() {
  return (
    <span aria-hidden="true" className="flex size-4 items-center justify-center">
      <span className="size-2 rounded-full bg-action" />
    </span>
  );
}
