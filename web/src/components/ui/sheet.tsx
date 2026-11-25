// A side sheet in the shape of shadcn/ui's, built on the native <dialog> instead of Radix
// Dialog: Radix locks the page scroll with a <style> element injected at run time, which the
// site's CSP blocks (style-src has no 'unsafe-inline'). showModal() gives the rest for free:
// focus moves in, the page behind is inert, Esc closes, and focus returns to the opener.
//
// The body mounts only while open, so the server HTML carries none of it (and none of the
// inline styles the Radix controls inside would put there).
import { type ReactNode, useEffect, useId, useRef } from "react";

import Icon from "@/components/Icon";
import { cn } from "@/lib/utils";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  children: ReactNode;
  /** Sticks to the bottom: the sheet's actions. */
  footer?: ReactNode;
  className?: string;
};

function Sheet({ open, onOpenChange, title, children, footer, className }: Props) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
    // The page behind must not scroll; a class, not a style attribute, so the CSP allows it.
    document.documentElement.classList.toggle("overflow-hidden", open);
    return () => document.documentElement.classList.remove("overflow-hidden");
  }, [open]);

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      onClose={() => onOpenChange(false)}
      // A click on the backdrop lands on the <dialog> itself; clicks inside land on children.
      onClick={(event) => {
        if (event.target === event.currentTarget) onOpenChange(false);
      }}
      className={cn(
        "fixed inset-y-0 right-0 left-auto m-0 h-dvh max-h-none w-full max-w-md border-0 bg-background p-0 text-foreground shadow-float backdrop:bg-bg-night/40",
        className,
      )}
    >
      <div className="flex h-full flex-col">
        <div className="flex items-center justify-between gap-4 border-b-(length:--border-width-default) border-border px-6 py-4">
          <h2 id={titleId} className="text-h3 text-text-heading-alt">
            {title}
          </h2>
          <button
            type="button"
            onClick={() => onOpenChange(false)}
            className="flex size-(--size-control-sm) items-center justify-center rounded-md text-text-primary outline-hidden hover:bg-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-solid focus-visible:outline-ring"
          >
            <Icon name="close-outline" size={20} label="Cerrar" />
          </button>
        </div>
        {open && <div className="flex-1 overflow-y-auto px-6 py-6">{children}</div>}
        {open && footer && (
          <div className="flex items-center justify-between gap-4 border-t-(length:--border-width-default) border-border px-6 py-4">
            {footer}
          </div>
        )}
      </div>
    </dialog>
  );
}

export { Sheet };
