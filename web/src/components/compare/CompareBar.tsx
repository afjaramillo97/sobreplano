// The floating "Comparar (N)" of the search (SPEC 11d): what is chosen, the way to the
// comparison and "Quitar todos". Below 1024 px it sits at the bottom, under "Ver mapa"; beside
// the map it floats over the list's column.
import { cx } from "class-variance-authority";

import { buttonVariants } from "@/components/ui/button-variants";
import { compareUrl, isComparisonFull, MAX_COMPARED, MIN_COMPARED } from "@/lib/compare-store";

type Props = {
  slugs: string[];
  memoryOnly: boolean;
  onClear: () => void;
};

export default function CompareBar({ slugs, memoryOnly, onClear }: Props) {
  return (
    <section
      aria-label="Comparador"
      className="fixed inset-x-4 bottom-4 z-30 mx-auto flex max-w-xl flex-wrap items-center justify-between gap-x-4 gap-y-2 rounded-md border-(length:--border-width-default) border-border-input bg-bg-surface px-4 py-3 shadow-float lg:right-12 lg:left-auto lg:mx-0"
    >
      <div className="flex flex-col">
        <p role="status" className="text-label text-text-primary">
          Comparar ({slugs.length})
        </p>
        {(slugs.length < MIN_COMPARED || isComparisonFull(slugs) || memoryOnly) && (
          <p className="text-caption text-text-muted">
            {slugs.length < MIN_COMPARED
              ? "Elige al menos 2 proyectos."
              : isComparisonFull(slugs)
                ? `Máximo ${MAX_COMPARED} proyectos.`
                : "Este navegador no guarda la selección."}
          </p>
        )}
      </div>
      <div className="flex items-center gap-4">
        <button
          type="button"
          onClick={onClear}
          className="cursor-pointer text-body-sm font-bold text-action-soft-text underline underline-offset-4 hover:text-action"
        >
          Quitar todos
        </button>
        {slugs.length >= MIN_COMPARED && (
          <a href={compareUrl(slugs)} className={cx(buttonVariants({ size: "sm" }))}>
            Ver comparación
          </a>
        )}
      </div>
    </section>
  );
}
