// shadcn/ui slider (Radix), adjusted to the kit: a 4 px lavender track, the range in the action
// color and white 24 px thumbs with a 2 px action border. Each thumb takes its own accessible
// name and value text, since a range has two.
import { Slider as SliderPrimitive } from "radix-ui";
import type * as React from "react";

import { cn } from "@/lib/utils";

type Props = React.ComponentProps<typeof SliderPrimitive.Root> & {
  /** One per thumb: "Precio mínimo", "Precio máximo". */
  thumbLabels: string[];
  /** How a value reads aloud: 250000000 → "$ 250 M". */
  valueText?: (value: number) => string;
};

function Slider({ className, value, defaultValue, thumbLabels, valueText, ...props }: Props) {
  const values = value ?? defaultValue ?? [];
  return (
    <SliderPrimitive.Root
      data-slot="slider"
      value={value}
      defaultValue={defaultValue}
      className={cn(
        "relative flex h-6 w-full touch-none items-center select-none data-[disabled]:opacity-50",
        className,
      )}
      {...props}
    >
      <SliderPrimitive.Track className="relative h-1 w-full grow overflow-hidden rounded-full bg-border-input">
        <SliderPrimitive.Range className="absolute h-full bg-primary" />
      </SliderPrimitive.Track>
      {values.map((v, i) => (
        <SliderPrimitive.Thumb
          key={thumbLabels[i] ?? i}
          aria-label={thumbLabels[i]}
          aria-valuetext={valueText?.(v)}
          className="block size-6 cursor-grab rounded-full border-(length:--border-width-strong) border-primary bg-background shadow-sm outline-hidden focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-solid focus-visible:outline-ring"
        />
      ))}
    </SliderPrimitive.Root>
  );
}

export { Slider };
