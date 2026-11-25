// The kit's search row (Search Result, Map v2): the search box and "Más filtros", then the
// quick filters (price, bedrooms, municipality, order), each in a popover that applies at once,
// then a chip per active filter.
//
// The triggers are plain buttons in the first bundle; the popovers load on first use, and the
// pointer or focus on a trigger starts that load early.
import { lazy, type ReactNode, type RefObject, Suspense, useId, useRef, useState } from "react";

import Icon from "@/components/Icon";
import { Button } from "@/components/ui/button";
import type { Municipality } from "@/lib/api/client";
import { MUNICIPALITY_NAMES } from "@/lib/projects";
import {
  clearFilters,
  type FilterChip,
  type PriceHistogram,
  Q_MAX_LENGTH,
  type SearchState,
} from "@/lib/search";
import { SORT_SHORT } from "./labels";
import type { QuickFilterKey } from "./QuickFilterPopover";
import type { HistoryWrite } from "./useSearchState";

const loadPopover = () => import("./QuickFilterPopover");
const QuickFilterPopover = lazy(loadPopover);

type Update = (change: (state: SearchState) => SearchState, write?: HistoryWrite) => void;

type TriggerProps = {
  triggerRef: RefObject<HTMLButtonElement | null>;
  label: ReactNode;
  active: boolean;
  expanded: boolean;
  controls: string;
  onToggle: () => void;
  icon?: "sort-outline";
};

/** A quick filter's trigger: the kit's 48 high outlined button, lavender while it has a value. */
function QuickFilterTrigger({ triggerRef, label, active, expanded, controls, onToggle, icon }: TriggerProps) {
  return (
    <button
      ref={triggerRef}
      type="button"
      aria-haspopup="dialog"
      aria-expanded={expanded}
      aria-controls={expanded ? controls : undefined}
      data-active={active}
      onClick={onToggle}
      onPointerEnter={loadPopover}
      onFocus={loadPopover}
      className="group inline-flex h-(--size-control-md) items-center gap-2 rounded-md border-(length:--border-width-default) border-border-input bg-bg-surface px-4 text-body-sm text-text-muted outline-hidden transition-colors duration-(--duration-fast) hover:border-action focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus-ring focus-visible:outline-solid aria-expanded:border-action data-[active=true]:border-action data-[active=true]:bg-action-soft data-[active=true]:font-bold data-[active=true]:text-action-soft-text motion-reduce:transition-none"
    >
      {icon && <Icon name={icon} size={20} className="text-action" />}
      {label}
      <span className="flex size-5 items-center justify-center rounded-full bg-action-soft text-action group-data-[active=true]:bg-bg-surface">
        <Icon
          name="chevron-down-outline"
          size={14}
          className="transition-transform duration-(--duration-fast) group-aria-expanded:rotate-180 motion-reduce:transition-none"
        />
      </span>
    </button>
  );
}

type Props = {
  state: SearchState;
  update: Update;
  chips: FilterChip[];
  histogram: PriceHistogram | null;
  municipalities: Municipality[];
  onOpenFilters: () => void;
  onPreloadFilters: () => void;
};

function municipalityLabel(selected: Municipality[]): string {
  if (selected.length === 0) return "Municipio";
  if (selected.length === 1) return MUNICIPALITY_NAMES[selected[0] as Municipality];
  return `${selected.length} municipios`;
}

export function FilterBar({
  state,
  update,
  chips,
  histogram,
  municipalities,
  onOpenFilters,
  onPreloadFilters,
}: Props) {
  const [open, setOpen] = useState<QuickFilterKey | null>(null);
  const popoverId = useId();
  const triggers: Record<QuickFilterKey, RefObject<HTMLButtonElement | null>> = {
    precio: useRef<HTMLButtonElement>(null),
    alcobas: useRef<HTMLButtonElement>(null),
    municipio: useRef<HTMLButtonElement>(null),
    orden: useRef<HTMLButtonElement>(null),
  };
  const priceChip = chips.find((chip) => chip.id === "precio");
  const trigger = (which: QuickFilterKey) => ({
    triggerRef: triggers[which],
    expanded: open === which,
    controls: popoverId,
    onToggle: () => setOpen((current) => (current === which ? null : which)),
  });

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-4 sm:flex-row">
        <form role="search" className="relative flex-1" onSubmit={(event) => event.preventDefault()}>
          <label htmlFor="buscar-proyectos" className="sr-only">
            Buscar por proyecto, barrio, municipio o constructora
          </label>
          <Icon
            name="search-outline"
            size={20}
            className="pointer-events-none absolute top-1/2 left-4 -translate-y-1/2 text-action"
          />
          <input
            id="buscar-proyectos"
            type="search"
            autoComplete="off"
            maxLength={Q_MAX_LENGTH}
            value={state.q}
            onChange={(event) => {
              const q = event.target.value;
              update((s) => ({ ...s, q }), "replace-later");
            }}
            placeholder="Proyecto, barrio o constructora"
            className="h-(--size-control-md) w-full rounded-md border-(length:--border-width-strong) border-border-input bg-bg-subtle pr-4 pl-12 text-body text-text-primary outline-hidden placeholder:text-text-muted focus-visible:border-action focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus-ring focus-visible:outline-solid"
          />
        </form>
        <Button
          type="button"
          onClick={onOpenFilters}
          onPointerEnter={onPreloadFilters}
          onFocus={onPreloadFilters}
        >
          <Icon name="filter-outline" size={20} />
          Más filtros
          {chips.length > 0 && (
            <span className="flex h-6 min-w-6 items-center justify-center rounded-full bg-bg-surface px-2 text-caption font-bold text-action-soft-text">
              {chips.length}
              <span className="sr-only">{chips.length === 1 ? " filtro activo" : " filtros activos"}</span>
            </span>
          )}
        </Button>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {histogram && (
          <QuickFilterTrigger
            {...trigger("precio")}
            label={priceChip ? priceChip.label.replace(/^Precio: /, "") : "Precio"}
            active={priceChip !== undefined}
          />
        )}
        <QuickFilterTrigger
          {...trigger("alcobas")}
          label={state.bedroomsMin === null ? "Alcobas" : `${state.bedroomsMin}+ alcobas`}
          active={state.bedroomsMin !== null}
        />
        <QuickFilterTrigger
          {...trigger("municipio")}
          label={municipalityLabel(state.municipalities)}
          active={state.municipalities.length > 0}
        />
        <div className="sm:ml-auto">
          <QuickFilterTrigger
            {...trigger("orden")}
            icon="sort-outline"
            label={
              <>
                <span className="sr-only">Ordenar: </span>
                {SORT_SHORT[state.sort]}
              </>
            }
            active={false}
          />
        </div>
      </div>

      {open && (
        <Suspense fallback={null}>
          <QuickFilterPopover
            which={open}
            id={popoverId}
            anchor={triggers[open]}
            onClose={() => setOpen(null)}
            state={state}
            update={update}
            histogram={histogram}
            municipalities={municipalities}
          />
        </Suspense>
      )}

      {chips.length > 0 && (
        <ul aria-label="Filtros activos" className="flex flex-wrap items-center gap-2">
          {chips.map((chip) => (
            <li key={chip.id}>
              <button
                type="button"
                aria-label={`Quitar filtro: ${chip.label}`}
                onClick={() => update(() => chip.without)}
                className="inline-flex h-8 items-center gap-1 rounded-full bg-action-soft pr-2 pl-3 text-body-sm font-bold text-action-soft-text outline-hidden transition-colors duration-(--duration-fast) hover:bg-bg-selected focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus-ring focus-visible:outline-solid motion-reduce:transition-none"
              >
                {chip.label}
                <Icon name="close-outline" size={16} />
              </button>
            </li>
          ))}
          <li>
            <button
              type="button"
              onClick={() => update(clearFilters)}
              className="h-8 rounded-md px-2 text-body-sm font-bold text-action-soft-text underline-offset-4 outline-hidden hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus-ring focus-visible:outline-solid"
            >
              Limpiar todo
            </button>
          </li>
        </ul>
      )}
    </div>
  );
}
