// shadcn/ui table, adjusted to the kit's price history table (medidas-kit-estatery §8.3):
// lavender header 56 high with radius 8 and 16/700 text, rows 76 high (24 of text, 26 above
// and below), 1.5 px dividers. No row hover: the tables are read, not clicked.
import type * as React from "react";

import { cn } from "@/lib/utils";

// With `label`, the scroll container becomes a named, focusable region: a table wider than
// the screen must be scrollable with the keyboard (axe: scrollable-region-focusable).
function Table({ className, label, ...props }: React.ComponentProps<"table"> & { label?: string }) {
  return (
    <div
      data-slot="table-container"
      className="relative w-full overflow-x-auto"
      {...(label ? { role: "region", "aria-label": label, tabIndex: 0 } : {})}
    >
      <table
        data-slot="table"
        className={cn("w-full caption-bottom text-body", className)}
        {...props}
      />
    </div>
  );
}

function TableHeader({ className, ...props }: React.ComponentProps<"thead">) {
  return (
    <thead
      data-slot="table-header"
      className={cn(
        "bg-bg-subtle [&_th:first-child]:rounded-l-md [&_th:last-child]:rounded-r-md",
        className,
      )}
      {...props}
    />
  );
}

function TableBody({ className, ...props }: React.ComponentProps<"tbody">) {
  return (
    <tbody
      data-slot="table-body"
      className={cn("[&_tr:last-child]:border-0", className)}
      {...props}
    />
  );
}

function TableFooter({ className, ...props }: React.ComponentProps<"tfoot">) {
  return (
    <tfoot
      data-slot="table-footer"
      className={cn(
        "border-t-(length:--border-width-default) border-border bg-bg-subtle font-bold",
        className,
      )}
      {...props}
    />
  );
}

function TableRow({ className, ...props }: React.ComponentProps<"tr">) {
  return (
    <tr
      data-slot="table-row"
      className={cn(
        "border-b-(length:--border-width-default) border-border [thead_&]:border-0",
        className,
      )}
      {...props}
    />
  );
}

function TableHead({ className, ...props }: React.ComponentProps<"th">) {
  return (
    <th
      data-slot="table-head"
      className={cn(
        "h-14 px-6 text-left align-middle text-label whitespace-nowrap text-text-primary",
        className,
      )}
      {...props}
    />
  );
}

function TableCell({ className, ...props }: React.ComponentProps<"td">) {
  return (
    <td
      data-slot="table-cell"
      className={cn("px-6 py-6.5 align-middle whitespace-nowrap text-text-secondary", className)}
      {...props}
    />
  );
}

function TableCaption({ className, ...props }: React.ComponentProps<"caption">) {
  return (
    <caption
      data-slot="table-caption"
      className={cn("mt-4 text-body-sm text-text-muted", className)}
      {...props}
    />
  );
}

export {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
};
