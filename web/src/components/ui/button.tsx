// shadcn/ui button, adjusted to the kit (medidas-kit-estatery §8.1): 40/48/56 high, radius 8,
// 16/700 text, solid focus outline (a ring at 50 % would fall under 3:1). No dark variants:
// the site has no dark mode yet, and dark: classes would half-apply on dark systems.
import { cva, type VariantProps } from "class-variance-authority";
import { Slot } from "radix-ui";
import type * as React from "react";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-2 rounded-md text-label whitespace-nowrap transition-colors duration-(--duration-fast) ease-out outline-hidden focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-offset-2 focus-visible:outline-ring disabled:pointer-events-none disabled:opacity-50 motion-reduce:transition-none [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-5",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-action-hover",
        dark: "bg-action-dark text-text-on-action hover:bg-action-dark/90",
        outline:
          "border-(length:--border-width-strong) border-border-input bg-background text-text-primary hover:bg-bg-subtle",
        soft: "border-(length:--border-width-default) border-border-input bg-bg-subtle text-action-soft-text hover:bg-action-soft",
        ghost: "text-text-primary hover:bg-accent",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-(--size-control-md) px-6 py-3",
        sm: "h-(--size-control-sm) px-4 py-2.5 text-body-sm font-bold [&_svg:not([class*='size-'])]:size-4",
        lg: "h-(--size-control-lg) px-8 py-4",
        icon: "size-(--size-control-md)",
        "icon-sm": "size-(--size-control-sm)",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

function Button({
  className,
  variant = "default",
  size = "default",
  asChild = false,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean;
  }) {
  const Comp = asChild ? Slot.Root : "button";

  return (
    <Comp
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  );
}

export { Button, buttonVariants };
