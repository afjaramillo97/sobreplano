// The filters of the "Más filtros" panel, loaded on first use: Radix's slider and checkbox are
// not needed to paint the listing (SPEC 11b, JavaScript budget).
import type { Municipality } from "@/lib/api/client";
import type { PriceHistogram, SearchState } from "@/lib/search";
import { AreaFilter, DeveloperFilter, MunicipalityFilter, PriceFilter, RoomsFilter } from "./filters";
import type { HistoryWrite } from "./useSearchState";

type Props = {
  state: SearchState;
  update: (change: (state: SearchState) => SearchState, write?: HistoryWrite) => void;
  histogram: PriceHistogram | null;
  areaRange: { min: number; max: number } | null;
  municipalities: Municipality[];
  developers: { slug: string; name: string }[];
};

export default function FiltersSheetBody({
  state,
  update,
  histogram,
  areaRange,
  municipalities,
  developers,
}: Props) {
  return (
    <div className="flex flex-col gap-8">
      <MunicipalityFilter
        options={municipalities}
        value={state.municipalities}
        onChange={(selected) => update((s) => ({ ...s, municipalities: selected }))}
      />
      <DeveloperFilter
        options={developers}
        value={state.developer}
        onChange={(developer) => update((s) => ({ ...s, developer }))}
      />
      {histogram && (
        <PriceFilter
          histogram={histogram}
          min={state.priceMin}
          max={state.priceMax}
          onChange={(priceMin, priceMax) => update((s) => ({ ...s, priceMin, priceMax }), "replace-later")}
        />
      )}
      <RoomsFilter
        legend="Alcobas"
        noun="alcobas"
        value={state.bedroomsMin}
        onChange={(bedroomsMin) => update((s) => ({ ...s, bedroomsMin }))}
      />
      <RoomsFilter
        legend="Baños"
        noun="baños"
        value={state.bathroomsMin}
        onChange={(bathroomsMin) => update((s) => ({ ...s, bathroomsMin }))}
      />
      {areaRange && (
        <AreaFilter
          range={areaRange}
          min={state.areaMin}
          max={state.areaMax}
          onChange={(areaMin, areaMax) => update((s) => ({ ...s, areaMin, areaMax }), "replace-later")}
        />
      )}
    </div>
  );
}
