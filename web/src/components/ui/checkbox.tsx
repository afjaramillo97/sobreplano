// shadcn/ui checkbox (Radix), adjusted to the kit: 20 px, 4 radius, filled in the action color
// when checked. The box is drawn in the action color even unchecked: the kit's lavender input
// border would fall under the 3:1 a control's boundary needs (DESIGN.md, rule 11).
import { Checkbox as CheckboxPrimitive } from "radix-ui";
import type * as React from "react";

import Icon from "@/components/Icon";
import { cn } from "@/lib/utils";

function Checkbox({ className, ...props }: React.ComponentProps<typeof CheckboxPrimitive.Root>) {
  return (
    <CheckboxPrimitive.Root
      data-slot="checkbox"
      className={cn(
        "peer size-5 shrink-0 rounded-sm border-(length:--border-width-strong) border-primary bg-background text-primary-foreground outline-hidden transition-colors duration-(--duration-fast) focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-solid focus-visible:outline-ring data-[state=checked]:bg-primary motion-reduce:transition-none",
        className,
      )}
      {...props}
    >
      <CheckboxPrimitive.Indicator className="flex items-center justify-center">
        <Icon name="check-outline" size={16} />
      </CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  );
}

export { Checkbox };
