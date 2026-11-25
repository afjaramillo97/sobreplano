// shadcn/ui tabs (Radix), adjusted to the kit (medidas-kit-estatery §8.5). Two variants:
// - default: the segmented control. Lavender track, 8 inset; the active item is white with a
//   2 px border and shadow-sm, 18/700.
// - line: tabs with an underline, 56 high, 3 px action line on the active one.
// The 6 px item radius is the kit's (8 minus the inset); it has no token of its own.
import { cva, type VariantProps } from "class-variance-authority";
import { Tabs as TabsPrimitive } from "radix-ui";
import type * as React from "react";

import { cn } from "@/lib/utils";

function Tabs({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.Root>) {
  return (
    <TabsPrimitive.Root
      data-slot="tabs"
      className={cn("flex flex-col gap-6", className)}
      {...props}
    />
  );
}

const tabsListVariants = cva("group/tabs-list inline-flex w-fit max-w-full items-center", {
  variants: {
    variant: {
      default:
        "gap-2 overflow-x-auto rounded-md border-(length:--border-width-default) border-border-input bg-bg-selected p-2",
      line: "h-14 overflow-x-auto border-b border-border-input",
    },
  },
  defaultVariants: {
    variant: "default",
  },
});

function TabsList({
  className,
  variant = "default",
  ...props
}: React.ComponentProps<typeof TabsPrimitive.List> & VariantProps<typeof tabsListVariants>) {
  return (
    <TabsPrimitive.List
      data-slot="tabs-list"
      data-variant={variant}
      className={cn(tabsListVariants({ variant }), className)}
      {...props}
    />
  );
}

function TabsTrigger({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.Trigger>) {
  return (
    <TabsPrimitive.Trigger
      data-slot="tabs-trigger"
      className={cn(
        "relative inline-flex shrink-0 items-center justify-center gap-2 text-body-lg whitespace-nowrap text-text-muted transition-colors duration-(--duration-fast) ease-out outline-none hover:text-text-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:pointer-events-none disabled:opacity-50 motion-reduce:transition-none data-[state=active]:font-bold data-[state=active]:text-text-primary [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-5",
        // Segmented control.
        "group-data-[variant=default]/tabs-list:h-(--size-control-md) group-data-[variant=default]/tabs-list:rounded-[calc(var(--radius-md)-2px)] group-data-[variant=default]/tabs-list:border-(length:--border-width-strong) group-data-[variant=default]/tabs-list:border-transparent group-data-[variant=default]/tabs-list:px-6 group-data-[variant=default]/tabs-list:data-[state=active]:border-border-input group-data-[variant=default]/tabs-list:data-[state=active]:bg-bg-surface group-data-[variant=default]/tabs-list:data-[state=active]:shadow-sm",
        // Underlined tabs.
        "group-data-[variant=line]/tabs-list:h-full group-data-[variant=line]/tabs-list:px-8 group-data-[variant=line]/tabs-list:after:absolute group-data-[variant=line]/tabs-list:after:inset-x-0 group-data-[variant=line]/tabs-list:after:-bottom-px group-data-[variant=line]/tabs-list:after:h-[3px] group-data-[variant=line]/tabs-list:after:bg-action group-data-[variant=line]/tabs-list:after:opacity-0 group-data-[variant=line]/tabs-list:data-[state=active]:after:opacity-100",
        className,
      )}
      {...props}
    />
  );
}

function TabsContent({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.Content>) {
  return (
    <TabsPrimitive.Content
      data-slot="tabs-content"
      className={cn(
        "flex-1 outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
        className,
      )}
      {...props}
    />
  );
}

export { Tabs, TabsContent, TabsList, TabsTrigger, tabsListVariants };
