// The shape of ui/select with the chevron drawn in CSS, for the finance and comparison islands:
// the icon of ui/select would bring every icon of the site into their JavaScript budget.
import type { ComponentProps } from "react";

export default function NativeSelect({ children, ...props }: ComponentProps<"select">) {
  return (
    <div className="relative">
      <select
        className="h-(--size-control-md) w-full cursor-pointer appearance-none rounded-md border-(length:--border-width-strong) border-input bg-muted py-2 pr-12 pl-4 text-body text-foreground outline-hidden focus-visible:border-ring focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-solid focus-visible:outline-ring"
        {...props}
      >
        {children}
      </select>
      <span
        aria-hidden="true"
        className="pointer-events-none absolute top-1/2 right-5 size-2 -translate-y-3/4 rotate-45 border-r-2 border-b-2 border-primary"
      />
    </div>
  );
}
