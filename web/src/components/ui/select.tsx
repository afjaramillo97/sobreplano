// A select in the shape of shadcn/ui's, on the native <select> instead of Radix Select: Radix
// injects <style> elements at run time (its viewport and its scroll lock), which the site's
// CSP blocks. The native one is also the one phones know how to show.
//
// Kit input: 48 high, 2 px lavender border, lavender fill and the action focus ring (DESIGN.md,
// rule 11), with the kit's chevron.
import type * as React from "react";

import Icon from "@/components/Icon";
import { cn } from "@/lib/utils";

function Select({ className, children, ...props }: React.ComponentProps<"select">) {
  return (
    <div className="relative">
      <select
        data-slot="select"
        className={cn(
          "h-(--size-control-md) w-full cursor-pointer appearance-none rounded-md border-(length:--border-width-strong) border-input bg-muted py-2 pr-12 pl-4 text-body text-foreground outline-hidden focus-visible:border-ring focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-solid focus-visible:outline-ring",
          className,
        )}
        {...props}
      >
        {children}
      </select>
      <Icon
        name="chevron-down-outline"
        size={20}
        className="pointer-events-none absolute top-1/2 right-4 -translate-y-1/2 text-primary"
      />
    </div>
  );
}

export { Select };
