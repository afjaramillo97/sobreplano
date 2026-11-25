// The content of a quick filter's popover, loaded with import() on first use: Radix's popover
// and slider are not needed to paint the listing, and they would put the page over its
// JavaScript budget (SPEC 11b). The trigger lives in FilterBar and stays put; the popover
// anchors to it.
import { type RefObject, useRef } from "react";

import { Popover, PopoverAnchor, PopoverContent } from "@/components/ui/popover";
import type { Municipality } from "@/lib/api/client";
import type { PriceHistogram, SearchState } from "@/lib/search";
import { MunicipalityFilter, PriceFilter, RoomsFilter, SortOptions } from "./filters";
import type { HistoryWrite } from "./useSearchState";

export type QuickFilterKey = "precio" | "alcobas" | "municipio" | "orden";

type Props = {
  which: QuickFilterKey;
  id: string;
  anchor: RefObject<HTMLButtonElement | null>;
  onClose: () => void;
  state: SearchState;
  update: (change: (state: SearchState) => SearchState, write?: HistoryWrite) => void;
  histogram: PriceHistogram | null;
  municipalities: Municipality[];
};

export default function QuickFilterPopover({
  which,
  id,
  anchor,
  onClose,
  state,
  update,
  histogram,
  municipalities,
}: Props) {
  // A click outside that lands somewhere else keeps its focus there; Esc goes back to the trigger.
  const clickedOutside = useRef(false);
  return (
    <Popover open onOpenChange={(open) => !open && onClose()}>
      <PopoverAnchor virtualRef={anchor} />
      <PopoverContent
        id={id}
        aria-label={LABELS[which]}
        className={which === "orden" ? "w-64 overflow-hidden p-0 py-2" : undefined}
        align={which === "orden" ? "end" : "start"}
        onInteractOutside={(event) => {
          // The trigger toggles the popover itself; closing here too would reopen it.
          if (event.target instanceof Node && anchor.current?.contains(event.target)) {
            event.preventDefault();
            return;
          }
          clickedOutside.current = true;
        }}
        onCloseAutoFocus={(event) => {
          event.preventDefault();
          if (!clickedOutside.current) anchor.current?.focus();
        }}
      >
        {which === "precio" && histogram && (
          <PriceFilter
            histogram={histogram}
            min={state.priceMin}
            max={state.priceMax}
            onChange={(priceMin, priceMax) => update((s) => ({ ...s, priceMin, priceMax }), "replace-later")}
          />
        )}
        {which === "alcobas" && (
          <RoomsFilter
            legend="Alcobas"
            noun="alcobas"
            value={state.bedroomsMin}
            onChange={(bedroomsMin) => update((s) => ({ ...s, bedroomsMin }))}
          />
        )}
        {which === "municipio" && (
          <MunicipalityFilter
            options={municipalities}
            value={state.municipalities}
            onChange={(selected) => update((s) => ({ ...s, municipalities: selected }))}
          />
        )}
        {which === "orden" && (
          <SortOptions
            value={state.sort}
            onChange={(sort) => {
              update((s) => ({ ...s, sort }));
              onClose();
            }}
          />
        )}
      </PopoverContent>
    </Popover>
  );
}

const LABELS: Record<QuickFilterKey, string> = {
  precio: "Precio",
  alcobas: "Alcobas",
  municipio: "Municipio",
  orden: "Ordenar",
};
