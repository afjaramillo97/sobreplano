// shadcn/ui skeleton, without the pulse: Tailwind's animate-pulse loops every 2 s, outside the
// 120-400 ms motion rule (web/DESIGN.md, rule 8). A still lavender block is enough.
import type * as React from "react";

import { cn } from "@/lib/utils";

function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div data-slot="skeleton" className={cn("rounded-md bg-bg-selected", className)} {...props} />
  );
}

export { Skeleton };
