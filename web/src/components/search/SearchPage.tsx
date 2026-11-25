// The search on /proyectos/ (SPEC 11b): filters kept in the URL, the cards of the projects that
// pass them, the empty state and, from 1024 px, the map at the left as in the kit's Search
// Result (Map v2). One island (client:load); its server render is the whole catalog without
// filters, so the page works and is indexed without JavaScript.
import { lazy, Suspense, useEffect, useMemo, useState } from "react";

import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { formatCount } from "@/lib/format";
import {
  activeChips,
  areaRange,
  type Bounds,
  clearFilters,
  developerOptions,
  hasUnitFilters,
  municipalityOptions,
  priceHistogram,
  type SearchItem,
  type SortKey,
  searchResults,
  splitByBounds,
} from "@/lib/search";
import { FilterBar } from "./FilterBar";
import { FiltersSheet, preloadFiltersSheet } from "./FiltersSheet";
import { ResultCards } from "./ResultCards";
import { useSearchState } from "./useSearchState";

// MapLibre is most of the map's weight: it loads only when the map is shown.
const ResultsMap = lazy(() => import("./ResultsMap"));

const LIST_ID = "resultados";

const SORT_DESCRIPTIONS: Record<SortKey, string> = {
  precio:
    "Ordenados por precio desde, del más bajo al más alto. Los que no tienen precio publicado van al final.",
  precio_desc:
    "Ordenados por precio desde, del más alto al más bajo. Los que no tienen precio publicado van al final.",
  subida:
    "Ordenados por cuánto ha subido su precio desde el primero que observamos. Los que no tienen variación van al final.",
  nombre: "Ordenados por nombre.",
};

// The card grid: three columns without the map, one or two in the panel beside it.
const GRID = "lg:no-js:grid-cols-3 lg:js:grid-cols-1 xl:js:grid-cols-2";

/** Whether a media query matches; false on the server and until hydration. */
function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(false);
  useEffect(() => {
    const list = window.matchMedia(query);
    const sync = () => setMatches(list.matches);
    sync();
    list.addEventListener("change", sync);
    return () => list.removeEventListener("change", sync);
  }, [query]);
  return matches;
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

  const isDesktop = useMediaQuery("(min-width: 1024px)");
  const mapShown = ready && isDesktop;
  const [mapStatus, setMapStatus] = useState<"loading" | "ready" | "error">("loading");
  const [bounds, setBounds] = useState<Bounds | null>(null);
  const [highlighted, setHighlighted] = useState<string | null>(null);
  const [selectedSlug, setSelected] = useState<string | null>(null);
  // A project the filters drop takes its floating card with it.
  const selected = selectedSlug && results.some((r) => r.item.slug === selectedSlug) ? selectedSlug : null;

  // The render after the URL was read is on screen: the skeletons can go.
  useEffect(() => {
    if (ready) delete document.documentElement.dataset.searchPending;
  }, [ready]);

  // A map that goes away (the window narrows) loads again from scratch.
  useEffect(() => {
    if (!mapShown) {
      setMapStatus("loading");
      setBounds(null);
    }
  }, [mapShown]);

  const zone = useMemo(() => (bounds ? splitByBounds(results, bounds) : null), [results, bounds]);
  // The map filters the list only on a desktop, with "Buscar al mover el mapa" on and the map
  // drawn; a map that failed leaves every result in the list.
  const mapFilters = mapShown && state.searchOnMove && mapStatus === "ready" && zone !== null;
  const listed = mapFilters && zone ? zone.inside : results;
  const unlocated = mapFilters && zone ? zone.unlocated : [];

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

  const shownCount = listed.length + unlocated.length;
  return (
    <div className="lg:js:grid lg:js:grid-cols-2 xl:js:grid-cols-[minmax(0,1fr)_46rem]">
      {/* The map column exists only with JavaScript, from the first paint, so nothing shifts. */}
      <section
        aria-label="Mapa de resultados"
        className="hidden lg:js:sticky lg:js:top-(--size-nav) lg:js:block lg:js:h-[calc(100dvh-var(--size-nav))] lg:js:self-start lg:js:py-8 lg:js:pl-12"
      >
        {mapShown ? (
          <Suspense fallback={<Skeleton className="h-full rounded-lg" />}>
            <ResultsMap
              className="h-full"
              results={results}
              initialView={state.map}
              inZone={zone?.inside.length ?? 0}
              highlighted={highlighted}
              selected={selected}
              searchOnMove={state.searchOnMove}
              onSearchOnMoveChange={(searchOnMove) => update((s) => ({ ...s, searchOnMove }))}
              onHighlight={setHighlighted}
              onSelect={setSelected}
              onViewChange={(next, view, byUser) => {
                setBounds(next);
                if (byUser) {
                  const map = {
                    lat: Number(view.lat.toFixed(4)),
                    lon: Number(view.lon.toFixed(4)),
                    zoom: Number(view.zoom.toFixed(1)),
                  };
                  update((s) => ({ ...s, map }), "replace-later");
                }
              }}
              onStatus={setMapStatus}
              listId={LIST_ID}
            />
          </Suspense>
        ) : (
          <Skeleton className="h-full rounded-lg" />
        )}
      </section>

      <div className="page py-12 lg:py-20 lg:js:mx-0 lg:js:max-w-none lg:js:px-12 lg:js:py-8">
        <h1 className="text-h2 text-text-heading-alt search-pending:invisible">
          {formatCount(shownCount, "proyecto", "proyectos")}
        </h1>
        <p className="mt-2 max-w-2xl text-body text-text-secondary">
          {SORT_DESCRIPTIONS[state.sort]}
          {hasUnitFilters(state) &&
            " El precio desde de cada proyecto es el de su tipología más barata que cumple tus filtros."}
        </p>
        {/* Announces what the filters leave, only after the reader changes something; the map
            announces its own zone. */}
        <p role="status" className="sr-only">
          {ready && changed ? formatCount(results.length, "proyecto cumple", "proyectos cumplen") : ""}
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

        <div id={LIST_ID} tabIndex={-1} className="mt-12 outline-hidden">
          {/* A URL with filters shows these until the island has read it (no flash of the
              unfiltered list). Same size as the cards. */}
          <ul aria-hidden="true" className={`hidden gap-8 search-pending:grid md:grid-cols-2 ${GRID}`}>
            {items.slice(0, 6).map((item) => (
              <li key={item.slug}>
                <Skeleton className="h-[29rem]" />
              </li>
            ))}
          </ul>
          <div className="search-pending:hidden">
            {results.length === 0 ? (
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
            ) : (
              <>
                {listed.length > 0 ? (
                  <ResultCards
                    results={listed}
                    priority
                    highlighted={highlighted}
                    onHighlight={mapShown ? setHighlighted : undefined}
                    className={GRID}
                  />
                ) : (
                  <p className="text-body text-text-secondary">
                    Ningún proyecto con ubicación cae en esta zona del mapa. Aleja el mapa o
                    muévelo para ver más.
                  </p>
                )}
                {unlocated.length > 0 && (
                  <section aria-labelledby="sin-ubicacion" className="mt-12">
                    <h2 id="sin-ubicacion" className="text-h3 text-text-primary">
                      Sin ubicación publicada ({unlocated.length})
                    </h2>
                    <p className="mt-2 text-body text-text-secondary">
                      Su constructora no publica el mapa, así que no salen en él.
                    </p>
                    <ResultCards results={unlocated} headingLevel={3} className={`mt-8 ${GRID}`} />
                  </section>
                )}
              </>
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
    </div>
  );
}
