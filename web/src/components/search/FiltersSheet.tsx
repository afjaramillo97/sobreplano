// The kit's "Más filtros" panel (Search Result - Filter, Map v2): every filter, applied at once,
// with a live count and the "Limpiar" and "Ver N proyectos" actions. The filters themselves load
// on first use (preloadFiltersSheet starts it when the pointer or focus reaches the button).
import { lazy, Suspense } from "react";

import { Button } from "@/components/ui/button";
import { Sheet } from "@/components/ui/sheet";
import type { Municipality } from "@/lib/api/client";
import { formatCount } from "@/lib/format";
import { clearFilters, type PriceHistogram, type SearchState } from "@/lib/search";
import type { HistoryWrite } from "./useSearchState";

/** Starts loading the panel's filters. */
export const preloadFiltersSheet = () => import("./FiltersSheetBody");
const FiltersSheetBody = lazy(preloadFiltersSheet);

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  state: SearchState;
  update: (change: (state: SearchState) => SearchState, write?: HistoryWrite) => void;
  count: number;
  histogram: PriceHistogram | null;
  areaRange: { min: number; max: number } | null;
  municipalities: Municipality[];
  developers: { slug: string; name: string }[];
};

export function FiltersSheet({
  open,
  onOpenChange,
  state,
  update,
  count,
  histogram,
  areaRange,
  municipalities,
  developers,
}: Props) {
  const countText = formatCount(count, "proyecto", "proyectos");
  return (
    <Sheet
      open={open}
      onOpenChange={onOpenChange}
      title="Más filtros"
      footer={
        <>
          <Button type="button" variant="outline" onClick={() => update(clearFilters)}>
            Limpiar
          </Button>
          <Button type="button" onClick={() => onOpenChange(false)}>
            Ver {countText}
          </Button>
        </>
      }
    >
      {/* The page behind is inert while the sheet is open, so its live count is not heard. */}
      <p role="status" className="sr-only">
        {countText}
      </p>
      <Suspense fallback={<p className="text-body text-text-secondary">Cargando filtros…</p>}>
        <FiltersSheetBody
          state={state}
          update={update}
          histogram={histogram}
          areaRange={areaRange}
          municipalities={municipalities}
          developers={developers}
        />
      </Suspense>
    </Sheet>
  );
}
