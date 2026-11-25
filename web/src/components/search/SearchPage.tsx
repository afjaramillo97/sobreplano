// The search on /proyectos/ (SPEC 11b): filters kept in the URL, the cards of the projects that
// pass them, and the empty state. One island (client:load); its server render is the whole
// catalog without filters, so the page works and is indexed without JavaScript.
import { useEffect, useMemo, useState } from "react";

import ProjectCard, { type CardUnit } from "@/components/ProjectCard";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { formatCount } from "@/lib/format";
import {
  activeChips,
  areaRange,
  clearFilters,
  developerOptions,
  hasUnitFilters,
  municipalityOptions,
  priceHistogram,
  type SearchItem,
  type SearchResult,
  type SortKey,
  searchResults,
} from "@/lib/search";
import { FilterBar } from "./FilterBar";
import { FiltersSheet, preloadFiltersSheet } from "./FiltersSheet";
import { useSearchState } from "./useSearchState";

const SORT_DESCRIPTIONS: Record<SortKey, string> = {
  precio:
    "Ordenados por precio desde, del más bajo al más alto. Los que no tienen precio publicado van al final.",
  precio_desc:
    "Ordenados por precio desde, del más alto al más bajo. Los que no tienen precio publicado van al final.",
  subida:
    "Ordenados por cuánto ha subido su precio desde el primero que observamos. Los que no tienen variación van al final.",
  nombre: "Ordenados por nombre.",
};

/** The "desde" a card shows: the unit type that passes the search, priced on its project's day. */
function cardUnit({ item, from }: SearchResult): CardUnit | null {
  return from ? { ...from, observedOn: item.lastObservedOn } : null;
}

export function ResultCards({ results, headingLevel = 2 }: { results: SearchResult[]; headingLevel?: 2 | 3 }) {
  return (
    <ul className="grid gap-8 md:grid-cols-2 lg:grid-cols-3">
      {results.map((result, i) => (
        <li key={result.item.slug}>
          <ProjectCard
            project={result.item}
            from={cardUnit(result)}
            priority={i === 0 && headingLevel === 2}
            headingLevel={headingLevel}
          />
        </li>
      ))}
    </ul>
  );
}

export default function SearchPage({ items }: { items: SearchItem[] }) {
  const developers = useMemo(() => developerOptions(items), [items]);
  const developerSlugs = useMemo(() => developers.map((d) => d.slug), [developers]);
  const developerNames = useMemo(() => new Map(developers.map((d) => [d.slug, d.name])), [developers]);
  const municipalities = useMemo(() => municipalityOptions(items), [items]);
  const areas = useMemo(() => areaRange(items), [items]);
  const { state, update, ready, changed } = useSearchState(developerSlugs);
  const results = useMemo(() => searchResults(items, state), [items, state]);
  const histogram = useMemo(() => priceHistogram(items, state), [items, state]);
  const chips = activeChips(state, developerNames);
  const [filtersOpen, setFiltersOpen] = useState(false);

  // The render after the URL was read is on screen: the skeletons can go.
  useEffect(() => {
    if (ready) delete document.documentElement.dataset.searchPending;
  }, [ready]);

  if (items.length === 0) {
    return (
      <div className="page py-12 lg:py-20">
        <h1 className="text-h2 text-text-heading-alt">0 proyectos</h1>
        <div className="mt-12 flex flex-col items-start gap-4">
          <p className="text-body text-text-secondary">
            Todavía no hay proyectos en el catálogo. Vuelve pronto: lo actualizamos cada día.
          </p>
          <a href="/" className={buttonVariants({ variant: "outline" })}>
            Ir al inicio
          </a>
        </div>
      </div>
    );
  }

  const countText = formatCount(results.length, "proyecto", "proyectos");
  return (
    <div className="page py-12 lg:py-20">
      <h1 className="text-h2 text-text-heading-alt search-pending:invisible">{countText}</h1>
      <p className="mt-2 max-w-2xl text-body text-text-secondary">
        {SORT_DESCRIPTIONS[state.sort]}
        {hasUnitFilters(state) &&
          " El precio desde de cada proyecto es el de su tipología más barata que cumple tus filtros."}
      </p>
      {/* Announced only after the reader changes something, not on load. */}
      <p role="status" className="sr-only">
        {ready && changed ? countText : ""}
      </p>

      {/* Without JavaScript the controls would do nothing, so they show only with it. */}
      <div className="mt-8 hidden js:block">
        <FilterBar
          state={state}
          update={update}
          chips={chips}
          histogram={histogram}
          municipalities={municipalities}
          onOpenFilters={() => setFiltersOpen(true)}
          onPreloadFilters={preloadFiltersSheet}
        />
      </div>

      <div className="mt-12">
        {/* A URL with filters shows these until the island has read it (no flash of the
            unfiltered list). Same size as the cards. */}
        <ul aria-hidden="true" className="hidden gap-8 search-pending:grid md:grid-cols-2 lg:grid-cols-3">
          {items.slice(0, 6).map((item) => (
            <li key={item.slug}>
              <Skeleton className="h-[29rem]" />
            </li>
          ))}
        </ul>
        <div className="search-pending:hidden">
          {results.length > 0 ? (
            <ResultCards results={results} />
          ) : (
            <div className="flex flex-col items-start gap-4 rounded-md border-(length:--border-width-default) border-border bg-bg-subtle p-8">
              <h2 className="text-h3 text-text-primary">Ningún proyecto cumple estos filtros</h2>
              <p className="text-body text-text-secondary">
                Quita alguno de los filtros de arriba o empieza de nuevo con todos los proyectos.
              </p>
              <button
                type="button"
                onClick={() => update(clearFilters)}
                className={buttonVariants({ variant: "outline" })}
              >
                Limpiar todo
              </button>
            </div>
          )}
        </div>
      </div>

      <FiltersSheet
        open={filtersOpen}
        onOpenChange={setFiltersOpen}
        state={state}
        update={update}
        count={results.length}
        histogram={histogram}
        areaRange={areas}
        municipalities={municipalities}
        developers={developers}
      />
    </div>
  );
}
