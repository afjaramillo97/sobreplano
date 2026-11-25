// The results map (SPEC 11b), loaded with import() only when it is shown. MapLibre GL JS on
// OpenFreeMap's Positron, repainted with the map tokens; one HTML <button> per project, with
// its "desde" and its change, so the keyboard reaches every pill; nearby pills grouped with
// Supercluster. The list stays the accessible alternative: "Saltar el mapa" jumps to it.
import "maplibre-gl/dist/maplibre-gl.css";

import {
  AttributionControl,
  LngLatBounds,
  type Map as MapLibreMap,
  Map as MapLibreMapClass,
  Marker,
  setWorkerUrl,
  type StyleSpecification,
} from "maplibre-gl";
// The worker is served from the site (worker-src 'self'), not built from a blob: URL.
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import Supercluster, { type ClusterProperties } from "supercluster";

import Icon from "@/components/Icon";
import ProjectCard from "@/components/ProjectCard";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import { formatCount } from "@/lib/format";
import { ATTRIBUTION, type MapColors, repaintStyle, STYLE_URL } from "@/lib/map-style";
import { type Bounds, type MapView, pillLabel, pillText, type SearchResult } from "@/lib/search";
import { cn } from "@/lib/utils";
import { cardUnit } from "./ResultCards";

setWorkerUrl(workerUrl);

/** Where the map opens when no project has coordinates: Medellín. */
const FALLBACK_VIEW: MapView = { lat: 6.2442, lon: -75.5812, zoom: 11 };
// Room above for the counter box and below for the attribution.
const FIT_PADDING = { top: 120, bottom: 64, left: 64, right: 64 };
const FIT_MAX_ZOOM = 14;
/** Pills closer than this, in px, join a group. A pill is about 150 px wide. */
const CLUSTER_RADIUS = 72;
const CLUSTER_MAX_ZOOM = 17;

const PILL_CLASS =
  "rounded-full border-(length:--border-width-strong) border-transparent bg-map-pill px-4 py-1.5 text-price-pill whitespace-nowrap text-map-pill-text shadow-sm outline-hidden transition-colors duration-(--duration-fast) hover:border-action focus-visible:border-action focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus-ring focus-visible:outline-solid data-[highlighted=true]:border-action data-[selected=true]:bg-map-pill-selected data-[selected=true]:text-text-on-action motion-reduce:transition-none";
const CLUSTER_CLASS =
  "flex size-11 items-center justify-center rounded-full border-(length:--border-width-strong) border-bg-surface bg-action-dark text-label text-text-on-night shadow-sm outline-hidden hover:bg-action focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus-ring focus-visible:outline-solid";

type Point = { slug: string };

type Props = {
  /** The projects that pass the filters; those with coordinates get a pill. */
  results: SearchResult[];
  /** The view in the URL, if any; otherwise the map frames every pill. */
  initialView: MapView | null;
  /** How many pills are inside the visible map, for the counter. */
  inZone: number;
  highlighted: string | null;
  selected: string | null;
  searchOnMove: boolean;
  onSearchOnMoveChange: (value: boolean) => void;
  onHighlight: (slug: string | null) => void;
  onSelect: (slug: string | null) => void;
  /** After every move; `byUser` is false for the first framing and for resizes. */
  onViewChange: (bounds: Bounds, view: MapView, byUser: boolean) => void;
  onStatus: (status: "ready" | "error") => void;
  /** Where the list starts, for "Saltar el mapa". */
  listId: string;
  className?: string;
  /** Extra controls over the map (the "Ver lista" bar on phones). */
  children?: ReactNode;
};

/** The map tokens as the page resolved them (global.css declares --map-*). */
function readColors(): MapColors {
  const css = getComputedStyle(document.documentElement);
  const read = (name: string) => css.getPropertyValue(name).trim();
  return { land: read("--map-land"), park: read("--map-park"), water: read("--map-water") };
}

function viewOf(map: MapLibreMap): { bounds: Bounds; view: MapView } {
  const b = map.getBounds();
  const center = map.getCenter();
  return {
    bounds: { west: b.getWest(), south: b.getSouth(), east: b.getEast(), north: b.getNorth() },
    view: { lat: center.lat, lon: center.lng, zoom: map.getZoom() },
  };
}

// MapLibre passes the DOM event of a gesture (drag, wheel, keys) as originalEvent; the zoom
// buttons and the groups pass { user: true }.
function byUser(event: object): boolean {
  return Boolean(
    ("originalEvent" in event && event.originalEvent) || ("user" in event && event.user),
  );
}

export default function ResultsMap(props: Props) {
  const {
    results,
    inZone,
    highlighted,
    selected,
    searchOnMove,
    onSearchOnMoveChange,
    onSelect,
    listId,
    className,
    children,
  } = props;
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const markers = useRef(new Map<string, { marker: Marker; element: HTMLButtonElement }>());
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  // Bumped after each move, so the groups are worked out again for the new view.
  const [moves, setMoves] = useState(0);
  // Handlers attached once read the latest props through this.
  const latest = useRef(props);
  latest.current = props;

  const located = useMemo(() => results.filter((r) => r.item.location !== null), [results]);
  const bySlug = useMemo(() => new Map(located.map((r) => [r.item.slug, r])), [located]);
  const index = useMemo(() => {
    const clusters = new Supercluster<Point, Point>({ radius: CLUSTER_RADIUS, maxZoom: CLUSTER_MAX_ZOOM });
    clusters.load(
      located.map((r) => ({
        type: "Feature" as const,
        geometry: { type: "Point" as const, coordinates: [r.item.location?.lon ?? 0, r.item.location?.lat ?? 0] },
        properties: { slug: r.item.slug },
      })),
    );
    return clusters;
  }, [located]);
  // Marker handlers outlive a rebuilt index; they read the current one.
  const indexRef = useRef(index);
  indexRef.current = index;

  // The map itself, once. Its first view comes from the URL or frames every pill.
  useEffect(() => {
    let cancelled = false;
    let map: MapLibreMap | undefined;
    const fail = () => {
      if (cancelled) return;
      setStatus("error");
      latest.current.onStatus("error");
    };
    (async () => {
      let style: StyleSpecification;
      try {
        const response = await fetch(STYLE_URL);
        if (!response.ok) throw new Error(`map style: ${response.status}`);
        style = repaintStyle((await response.json()) as StyleSpecification, readColors());
      } catch {
        fail();
        return;
      }
      if (cancelled || !container.current) return;
      const start = latest.current.initialView;
      const points = latest.current.results.flatMap((r) => (r.item.location ? [r.item.location] : []));
      const frame =
        start === null && points.length > 0
          ? points.reduce(
              (b, p) => b.extend([p.lon, p.lat]),
              new LngLatBounds([points[0]?.lon ?? 0, points[0]?.lat ?? 0], [points[0]?.lon ?? 0, points[0]?.lat ?? 0]),
            )
          : null;
      const view = start ?? FALLBACK_VIEW;
      try {
        map = new MapLibreMapClass({
          container: container.current,
          style,
          attributionControl: false,
          ...(frame
            ? { bounds: frame, fitBoundsOptions: { padding: FIT_PADDING, maxZoom: FIT_MAX_ZOOM } }
            : { center: [view.lon, view.lat] as [number, number], zoom: view.zoom }),
          maxZoom: 18,
          dragRotate: false,
          pitchWithRotate: false,
          touchPitch: false,
          locale: {
            "Map.Title":
              "Mapa de los proyectos. Usa las flechas para moverlo y las teclas más y menos para acercarlo o alejarlo.",
          },
        });
      } catch {
        // No WebGL, or a browser MapLibre does not support.
        fail();
        return;
      }
      mapRef.current = map;
      map.touchZoomRotate.disableRotation();
      map.keyboard.disableRotation();
      map.addControl(new AttributionControl({ compact: false, customAttribution: ATTRIBUTION }), "bottom-right");
      let loaded = false;
      map.on("error", () => {
        // A style or tile that never arrives before the first paint means no map at all.
        if (!loaded) fail();
      });
      map.once("load", () => {
        if (cancelled || !map) return;
        loaded = true;
        setStatus("ready");
        latest.current.onStatus("ready");
        const { bounds, view: shown } = viewOf(map);
        latest.current.onViewChange(bounds, shown, false);
        setMoves((n) => n + 1);
      });
      map.on("moveend", (event) => {
        if (!loaded || !map) return;
        const { bounds, view: shown } = viewOf(map);
        latest.current.onViewChange(bounds, shown, byUser(event));
        setMoves((n) => n + 1);
      });
      map.on("click", (event) => {
        // A click on the map itself, not on a pill, closes the floating card.
        if (event.originalEvent.target === map?.getCanvas()) latest.current.onSelect(null);
      });
    })();
    return () => {
      cancelled = true;
      for (const { marker } of markers.current.values()) marker.remove();
      markers.current.clear();
      map?.remove();
      mapRef.current = null;
    };
  }, []);

  // The pills and groups of the visible map, kept in step with the results and the view.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || status !== "ready") return;
    const b = map.getBounds();
    const features = index.getClusters(
      [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()],
      Math.floor(map.getZoom()),
    );
    const seen = new Set<string>();
    for (const feature of features) {
      const [lon = 0, lat = 0] = feature.geometry.coordinates;
      const properties = feature.properties as Point & Partial<ClusterProperties>;
      const isCluster = properties.cluster === true;
      const key = isCluster ? `c:${properties.cluster_id}` : `p:${properties.slug}`;
      seen.add(key);
      let entry = markers.current.get(key);
      if (!entry) {
        // MapLibre owns the wrapper's classes and transform; the button inside is ours.
        const wrapper = document.createElement("div");
        const element = document.createElement("button");
        element.type = "button";
        wrapper.append(element);
        element.addEventListener("click", (event) => {
          event.stopPropagation();
          const target = event.currentTarget as HTMLButtonElement;
          if (target.dataset.cluster) {
            const zoom = indexRef.current.getClusterExpansionZoom(Number(target.dataset.cluster));
            const center: [number, number] = [Number(target.dataset.lon), Number(target.dataset.lat)];
            mapRef.current?.easeTo({ center, zoom }, { user: true });
          } else {
            const slug = target.dataset.slug ?? null;
            latest.current.onSelect(latest.current.selected === slug ? null : slug);
          }
        });
        element.addEventListener("pointerenter", () => latest.current.onHighlight(element.dataset.slug ?? null));
        element.addEventListener("pointerleave", () => latest.current.onHighlight(null));
        element.addEventListener("focus", () => latest.current.onHighlight(element.dataset.slug ?? null));
        element.addEventListener("blur", () => latest.current.onHighlight(null));
        const marker = new Marker({ element: wrapper, anchor: "center" }).setLngLat([lon, lat]).addTo(map);
        entry = { marker, element };
        markers.current.set(key, entry);
      }
      entry.marker.setLngLat([lon, lat]);
      const { element } = entry;
      if (isCluster) {
        const count = properties.point_count ?? 0;
        element.className = CLUSTER_CLASS;
        element.dataset.cluster = String(properties.cluster_id);
        element.dataset.lon = String(lon);
        element.dataset.lat = String(lat);
        delete element.dataset.slug;
        element.textContent = String(count);
        element.setAttribute("aria-label", `Grupo de ${count} proyectos. Acerca el mapa para separarlos.`);
        element.removeAttribute("aria-expanded");
      } else {
        const result = bySlug.get(properties.slug);
        if (!result) continue;
        element.className = PILL_CLASS;
        element.dataset.slug = properties.slug;
        delete element.dataset.cluster;
        element.textContent = pillText(result.from);
        element.setAttribute("aria-label", pillLabel(result.item, result.from));
        element.setAttribute("aria-expanded", String(selected === properties.slug));
        element.dataset.selected = String(selected === properties.slug);
        element.dataset.highlighted = String(highlighted === properties.slug);
        // The chosen or pointed pill draws over its neighbours.
        entry.marker.getElement().style.zIndex =
          selected === properties.slug ? "3" : highlighted === properties.slug ? "2" : "";
      }
    }
    for (const [key, { marker }] of markers.current) {
      if (!seen.has(key)) {
        marker.remove();
        markers.current.delete(key);
      }
    }
  }, [index, bySlug, status, moves, selected, highlighted]);

  const selectedResult = selected ? bySlug.get(selected) : undefined;
  const cardRef = useRef<HTMLDivElement>(null);

  /** Closes the floating card and gives the focus back to its pill. */
  const closeCard = () => {
    const slug = latest.current.selected;
    onSelect(null);
    if (slug) markers.current.get(`p:${slug}`)?.element.focus();
  };

  // The floating card takes the focus when it opens, so Esc and Tab work from there.
  useEffect(() => {
    if (selectedResult) cardRef.current?.querySelector<HTMLElement>("a")?.focus();
  }, [selectedResult]);

  const zoomBy = (delta: number) => {
    const map = mapRef.current;
    if (map) map.easeTo({ zoom: map.getZoom() + delta }, { user: true });
  };

  return (
    <div
      className={cn("relative isolate overflow-hidden rounded-lg bg-bg-selected", className)}
      onKeyDown={(event) => {
        if (event.key === "Escape" && latest.current.selected) {
          event.stopPropagation();
          closeCard();
        }
      }}
    >
      <a
        href={`#${listId}`}
        className="sr-only z-20 rounded-md bg-bg-surface px-4 py-2 text-label text-text-primary focus:not-sr-only focus:absolute focus:top-4 focus:left-4"
      >
        Saltar el mapa
      </a>
      {/* MapLibre makes this element position: relative, so it is sized, not inset. */}
      <div ref={container} className="h-full w-full" />

      {status === "loading" && <Skeleton className="absolute inset-0 rounded-none" />}

      {status === "error" ? (
        <div className="absolute inset-0 flex items-center justify-center p-8">
          <p role="alert" className="max-w-xs text-center text-body text-text-secondary">
            No pudimos cargar el mapa. La lista sigue funcionando.
          </p>
        </div>
      ) : (
        <>
          <div className="absolute top-4 left-4 z-10 flex flex-col gap-3 rounded-md border-(length:--border-width-default) border-border-input bg-bg-surface px-4 py-3 shadow-float">
            <p aria-live="polite" className="text-body-sm font-bold text-text-primary">
              {status === "ready"
                ? `${formatCount(inZone, "proyecto", "proyectos")} en esta zona del mapa`
                : "Cargando el mapa…"}
            </p>
            <div className="flex items-center gap-3">
              <Checkbox
                id="buscar-al-mover"
                checked={searchOnMove}
                onCheckedChange={(checked) => onSearchOnMoveChange(checked === true)}
              />
              <label htmlFor="buscar-al-mover" className="cursor-pointer text-body-sm text-text-secondary">
                Buscar al mover el mapa
              </label>
            </div>
          </div>

          <div className="absolute right-4 bottom-12 z-10 flex flex-col overflow-hidden rounded-md border-(length:--border-width-default) border-border-input bg-bg-surface shadow-float">
            <button
              type="button"
              onClick={() => zoomBy(1)}
              className="flex size-10 items-center justify-center text-text-primary outline-hidden hover:bg-bg-subtle focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-focus-ring focus-visible:outline-solid"
            >
              <Icon name="add-outline" size={16} label="Acercar" />
            </button>
            <span aria-hidden="true" className="h-px bg-border-input" />
            <button
              type="button"
              onClick={() => zoomBy(-1)}
              className="flex size-10 items-center justify-center text-text-primary outline-hidden hover:bg-bg-subtle focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-focus-ring focus-visible:outline-solid"
            >
              {/* The kit has no minus icon; our own line, on the same 24 px grid. */}
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" role="img" aria-label="Alejar">
                <path d="M4 12h16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              </svg>
            </button>
          </div>

          {selectedResult && (
            <div
              ref={cardRef}
              role="dialog"
              aria-label={selectedResult.item.name}
              className="absolute bottom-12 left-4 z-20 w-80 max-w-[calc(100%-2rem)] rounded-md shadow-float"
            >
              <ProjectCard project={selectedResult.item} from={cardUnit(selectedResult)} headingLevel={3} />
              <button
                type="button"
                onClick={closeCard}
                className="absolute top-3 right-3 flex size-8 items-center justify-center rounded-full bg-bg-surface text-text-primary shadow-sm outline-hidden hover:bg-bg-subtle focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus-ring focus-visible:outline-solid"
              >
                <Icon name="close-outline" size={16} label="Cerrar" />
              </button>
            </div>
          )}
        </>
      )}
      {children}
    </div>
  );
}
