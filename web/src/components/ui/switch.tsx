// The kit's Toggle (40 × 24 track, 20 px thumb) as a native button with role="switch", not
// Radix Switch: Radix renders a hidden input with a style attribute, which the CSP blocks.
// Off, the thumb is drawn in the action color: the kit's white thumb on the lavender track
// would fall under the 3:1 a control's state needs (DESIGN.md, rule 11).
import type * as React from "react";

import { cn } from "@/lib/utils";

type Props = Omit<React.ComponentProps<"button">, "onChange" | "role" | "aria-checked"> & {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
};

function Switch({ checked, onCheckedChange, className, ...props }: Props) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onCheckedChange(!checked)}
      className={cn(
        "relative inline-flex h-6 w-10 shrink-0 items-center rounded-full p-0.5 outline-hidden transition-colors duration-(--duration-fast) ease-out focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-solid focus-visible:outline-ring motion-reduce:transition-none",
        checked ? "bg-action" : "bg-border-input",
        className,
      )}
      {...props}
    >
      <span
        aria-hidden="true"
        className={cn(
          "size-5 rounded-full transition-transform duration-(--duration-fast) ease-out motion-reduce:transition-none",
          checked ? "translate-x-4 bg-bg-surface" : "translate-x-0 bg-action",
        )}
      />
    </button>
  );
}

export { Switch };
