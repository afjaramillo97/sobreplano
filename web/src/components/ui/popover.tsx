// shadcn/ui popover (Radix), adjusted to the kit's dropdowns: white, 8 radius, 1.5 px lavender
// border, shadow-float. Always non-modal: a modal Radix popover locks the page scroll with a
// <style> element injected at run time, which the site's CSP blocks (style-src has no
// 'unsafe-inline').
import { Popover as PopoverPrimitive } from "radix-ui";
import type * as React from "react";

import { cn } from "@/lib/utils";

function Popover(props: Omit<React.ComponentProps<typeof PopoverPrimitive.Root>, "modal">) {
  return <PopoverPrimitive.Root data-slot="popover" modal={false} {...props} />;
}

function PopoverTrigger(props: React.ComponentProps<typeof PopoverPrimitive.Trigger>) {
  return <PopoverPrimitive.Trigger data-slot="popover-trigger" {...props} />;
}

/** Anchors the content to an element outside the popover (its trigger, when that lives apart). */
function PopoverAnchor(props: React.ComponentProps<typeof PopoverPrimitive.Anchor>) {
  return <PopoverPrimitive.Anchor data-slot="popover-anchor" {...props} />;
}

function PopoverContent({
  className,
  align = "start",
  sideOffset = 8,
  ...props
}: React.ComponentProps<typeof PopoverPrimitive.Content>) {
  return (
    <PopoverPrimitive.Portal>
      <PopoverPrimitive.Content
        data-slot="popover-content"
        align={align}
        sideOffset={sideOffset}
        collisionPadding={16}
        className={cn(
          "z-50 w-80 max-w-[calc(100vw-2rem)] rounded-md border-(length:--border-width-default) border-border-input bg-popover p-6 text-popover-foreground shadow-float outline-hidden",
          className,
        )}
        {...props}
      />
    </PopoverPrimitive.Portal>
  );
}

export { Popover, PopoverAnchor, PopoverContent, PopoverTrigger };
