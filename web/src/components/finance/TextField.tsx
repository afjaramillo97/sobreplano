// A finance field in the shape of the kit's input (48 high, 2 px lavender border, lavender
// fill), with its label always visible and its error beside it, announced with the field.
import { cx } from "class-variance-authority";
import { type ComponentProps, type ReactNode, useId, useState } from "react";

type Props = Omit<ComponentProps<"input">, "id" | "onChange" | "value" | "prefix"> & {
  label: string;
  value: string;
  onValue: (text: string) => void;
  prefix?: string;
  suffix?: string;
  hint?: ReactNode;
  /** Shown once the person leaves the field, not while they first type in it. */
  error?: string | null;
};

export default function TextField({
  label,
  value,
  onValue,
  prefix,
  suffix,
  hint,
  error,
  onBlur,
  className,
  ...inputProps
}: Props) {
  const id = useId();
  const [left, setLeft] = useState(false);
  const shown = left ? error : null;
  const describedBy =
    [hint ? `${id}-hint` : null, shown ? `${id}-error` : null].filter(Boolean).join(" ") ||
    undefined;
  return (
    <div className="flex flex-col gap-2">
      <label htmlFor={id} className="text-label text-text-primary">
        {label}
      </label>
      <div className="relative">
        {prefix && (
          <span
            aria-hidden="true"
            className="pointer-events-none absolute top-1/2 left-4 -translate-y-1/2 text-body text-text-muted"
          >
            {prefix}
          </span>
        )}
        <input
          id={id}
          type="text"
          // Income and savings stay on this device: no name to submit and nothing to autofill.
          autoComplete="off"
          value={value}
          onChange={(event) => onValue(event.target.value)}
          onBlur={(event) => {
            setLeft(true);
            onBlur?.(event);
          }}
          aria-invalid={shown ? true : undefined}
          aria-describedby={describedBy}
          className={cx(
            "h-(--size-control-md) w-full rounded-md border-(length:--border-width-strong) border-input bg-muted text-body text-foreground tabular-nums outline-hidden focus-visible:border-ring focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-solid focus-visible:outline-ring aria-invalid:border-destructive",
            prefix ? "pl-8" : "pl-4",
            suffix ? "pr-20" : "pr-4",
            className,
          )}
          {...inputProps}
        />
        {suffix && (
          <span
            aria-hidden="true"
            className="pointer-events-none absolute top-1/2 right-4 -translate-y-1/2 text-body-sm text-text-muted"
          >
            {suffix}
          </span>
        )}
      </div>
      {hint && (
        <p id={`${id}-hint`} className="text-body-sm text-text-muted">
          {hint}
        </p>
      )}
      {shown && (
        <p id={`${id}-error`} className="text-body-sm font-bold text-destructive">
          {shown}
        </p>
      )}
    </div>
  );
}
