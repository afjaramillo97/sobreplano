// The kit's Message bubbles: the person's on the right in lavender with the bottom-right corner
// square, the advisor's on the left in white with a 1.5 px border and the top-left corner
// square, next to a 48 px avatar. The time goes under the bubble.
import type { ReactNode } from "react";

import Icon from "@/components/Icon";
import { cn } from "@/lib/utils";

type Props = {
  from: "user" | "advisor";
  /** Under the bubble, as in the kit: the time, or a summary of the steps. */
  meta?: ReactNode;
  children: ReactNode;
  /** After the bubble, in the advisor's column: the project cards. */
  after?: ReactNode;
  className?: string;
};

export function Bubble({ from, meta, children, after, className }: Props) {
  if (from === "user") {
    return (
      <div className={cn("flex flex-col items-end gap-2", className)}>
        <div className="max-w-[85%] rounded-md rounded-br-none bg-border-input p-4 text-body-sm whitespace-pre-wrap text-text-primary sm:max-w-[75%]">
          <span className="sr-only">Tú: </span>
          {children}
        </div>
        {meta && <div className="text-body-sm text-text-muted">{meta}</div>}
      </div>
    );
  }
  return (
    <div className={cn("flex items-start gap-3 sm:gap-4", className)}>
      <AdvisorAvatar />
      <div className="flex min-w-0 flex-1 flex-col items-start gap-2">
        <div className="max-w-full rounded-md rounded-tl-none border-(length:--border-width-default) border-border-input bg-bg-surface p-4 text-body text-text-primary">
          <span className="sr-only">Asesor: </span>
          {children}
        </div>
        {meta && <div className="text-body-sm text-text-muted">{meta}</div>}
        {after}
      </div>
    </div>
  );
}

/** The advisor's avatar: the kit's 48 px circle, with the message icon instead of a photo. */
export function AdvisorAvatar({ className }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "hidden size-12 shrink-0 items-center justify-center rounded-full bg-bg-selected text-action sm:flex",
        className,
      )}
    >
      <Icon name="message-outline" size={24} />
    </span>
  );
}
