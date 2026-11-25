// shadcn/ui chart, trimmed for Sobreplano. The original ChartStyle injects a <style> element at
// run time, which the CSP blocks (SPEC 11a §11); here each series' color goes into a CSS
// variable through the style prop, which React sets through the CSSOM and the CSP allows.
// Only the container and the tooltip are kept: the history chart draws its own tooltip.
import * as React from "react";
import * as RechartsPrimitive from "recharts";

import { cn } from "@/lib/utils";

const INITIAL_DIMENSION = { width: 320, height: 200 } as const;

/** Series of a chart: their label and their color (a CSS value, such as a token variable). */
export type ChartConfig = Record<string, { label?: React.ReactNode; color?: string }>;

function ChartContainer({
  className,
  children,
  config,
  style,
  initialDimension = INITIAL_DIMENSION,
  ...props
}: React.ComponentProps<"div"> & {
  config: ChartConfig;
  children: React.ComponentProps<typeof RechartsPrimitive.ResponsiveContainer>["children"];
  initialDimension?: { width: number; height: number };
}) {
  // --color-<series> for each series, so marks can use stroke="var(--color-price)".
  const colors = Object.fromEntries(
    Object.entries(config)
      .filter(([, item]) => item.color)
      .map(([key, item]) => [`--color-${key}`, item.color]),
  ) as React.CSSProperties;

  return (
    <div
      data-slot="chart"
      className={cn(
        "flex justify-center text-caption [&_.recharts-cartesian-axis-tick_text]:fill-muted-foreground [&_.recharts-cartesian-grid_line]:stroke-border [&_.recharts-curve.recharts-tooltip-cursor]:stroke-border-input [&_.recharts-layer]:outline-hidden [&_.recharts-surface]:outline-hidden",
        className,
      )}
      style={{ ...colors, ...style }}
      {...props}
    >
      <RechartsPrimitive.ResponsiveContainer initialDimension={initialDimension}>
        {children}
      </RechartsPrimitive.ResponsiveContainer>
    </div>
  );
}

const ChartTooltip = RechartsPrimitive.Tooltip;

export { ChartContainer, ChartTooltip };
