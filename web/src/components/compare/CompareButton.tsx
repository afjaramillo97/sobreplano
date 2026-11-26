// "Agregar al comparador" on a project page (SPEC 11d), in the price card.
import { cx } from "class-variance-authority";

import { buttonVariants } from "@/components/ui/button-variants";
import {
  addToComparison,
  compareUrl,
  isComparisonFull,
  MAX_COMPARED,
  MIN_COMPARED,
  removeFromComparison,
} from "@/lib/compare-store";
import { useComparison } from "./useComparison";

const linkClass =
  "text-body-sm font-bold text-action-soft-text underline underline-offset-4 hover:text-action";

export default function CompareButton({ slug }: { slug: string }) {
  const { slugs, ready, memoryOnly, save } = useComparison();
  const chosen = slugs.includes(slug);
  const full = !chosen && isComparisonFull(slugs);
  return (
    <div className="flex flex-col gap-2">
      <button
        type="button"
        // Disabled until the selection is read, so a first click cannot overwrite it.
        disabled={!ready || full}
        onClick={() =>
          save(chosen ? removeFromComparison(slugs, slug) : addToComparison(slugs, slug))
        }
        className={cx(
          buttonVariants({ variant: "outline", size: "lg" }),
          "w-full cursor-pointer",
        )}
      >
        {chosen ? "Quitar del comparador" : "Agregar al comparador"}
      </button>
      <div role="status" className="flex flex-col items-center gap-1 text-center">
        {slugs.length >= MIN_COMPARED && (
          <a href={compareUrl(slugs)} className={linkClass}>
            Comparar ({slugs.length})
          </a>
        )}
        {chosen && slugs.length < MIN_COMPARED && (
          <p className="text-body-sm text-text-secondary">
            Agrega otro proyecto para comparar.{" "}
            <a href="/proyectos/" className={linkClass}>
              Buscar proyectos
            </a>
          </p>
        )}
        {full && (
          <p className="text-body-sm text-text-secondary">
            Ya elegiste {MAX_COMPARED} proyectos, el máximo.
          </p>
        )}
        {memoryOnly && (
          <p className="text-body-sm text-text-muted">Este navegador no guarda la selección.</p>
        )}
      </div>
    </div>
  );
}
