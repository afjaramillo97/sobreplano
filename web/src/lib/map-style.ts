/**
 * The base map (SPEC 11b): OpenFreeMap's Positron style, repainted with the map tokens, and the
 * attribution the site always shows. Pure, so tests/unit/map-style.test.ts pins it.
 */
import type { LayerSpecification, SourceSpecification, StyleSpecification } from "maplibre-gl";

/** OpenFreeMap's light style. Plan B: a PMTiles file in R2, changing only this URL. */
export const STYLE_URL = "https://tiles.openfreemap.org/styles/positron";

/**
 * The credit line, always visible (docs/terms-of-use.md). Exactly the attribution of
 * OpenFreeMap's tiles, so MapLibre shows it once: it drops an attribution that repeats another.
 */
export const ATTRIBUTION =
  '<a href="https://openfreemap.org" target="_blank">OpenFreeMap</a> ' +
  '<a href="https://www.openmaptiles.org/" target="_blank">&copy; OpenMapTiles</a> ' +
  'Data from <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a>';

export type MapColors = { land: string; park: string; water: string };

const PARK = /park|wood|forest|grass|scrub/;

function repaintLayer(layer: LayerSpecification, colors: MapColors): LayerSpecification {
  if (layer.type === "background") {
    return { ...layer, paint: { ...layer.paint, "background-color": colors.land } };
  }
  if (layer.type !== "fill") return layer;
  if (layer.id.includes("water")) {
    return { ...layer, paint: { ...layer.paint, "fill-color": colors.water } };
  }
  if (PARK.test(layer.id)) {
    return { ...layer, paint: { ...layer.paint, "fill-color": colors.park } };
  }
  return layer;
}

/**
 * The style with land, parks and water in the map tokens, and without its sources' own
 * attribution: the map shows ATTRIBUTION instead, so the line is the same with any style.
 */
export function repaintStyle(style: StyleSpecification, colors: MapColors): StyleSpecification {
  const sources: Record<string, SourceSpecification> = {};
  for (const [id, source] of Object.entries(style.sources)) {
    if ("attribution" in source) {
      const { attribution: _, ...rest } = source;
      sources[id] = rest as SourceSpecification;
    } else {
      sources[id] = source;
    }
  }
  return { ...style, sources, layers: style.layers.map((layer) => repaintLayer(layer, colors)) };
}
