import type { StyleSpecification } from "maplibre-gl";
import { describe, expect, it } from "vitest";
import { ATTRIBUTION, repaintStyle } from "../../src/lib/map-style";

const colors = { land: "land", park: "park", water: "water" };

const style: StyleSpecification = {
  version: 8,
  sources: {
    openmaptiles: { type: "vector", url: "https://example.com/planet", attribution: "© someone" },
    extra: { type: "geojson", data: { type: "FeatureCollection", features: [] } },
  },
  layers: [
    { id: "background", type: "background", paint: { "background-color": "white" } },
    { id: "water", type: "fill", source: "openmaptiles", "source-layer": "water", paint: { "fill-color": "blue", "fill-opacity": 0.5 } },
    { id: "park", type: "fill", source: "openmaptiles", "source-layer": "park", paint: { "fill-color": "green" } },
    { id: "landcover_wood", type: "fill", source: "openmaptiles", "source-layer": "landcover" },
    { id: "building", type: "fill", source: "openmaptiles", "source-layer": "building", paint: { "fill-color": "grey" } },
    { id: "waterway", type: "line", source: "openmaptiles", "source-layer": "waterway", paint: { "line-color": "blue" } },
  ],
};

describe("repaintStyle", () => {
  const repainted = repaintStyle(style, colors);
  const paint = (id: string) => repainted.layers.find((l) => l.id === id)?.paint as Record<string, unknown>;

  it("paints land, water and parks with the map tokens, keeping the rest of the paint", () => {
    expect(paint("background")["background-color"]).toBe("land");
    expect(paint("water")).toEqual({ "fill-color": "water", "fill-opacity": 0.5 });
    expect(paint("park")["fill-color"]).toBe("park");
    expect(paint("landcover_wood")["fill-color"]).toBe("park");
  });

  it("leaves other layers alone", () => {
    expect(paint("building")["fill-color"]).toBe("grey");
    expect(paint("waterway")["line-color"]).toBe("blue");
  });

  it("drops the sources' attribution, which the map replaces with its own line", () => {
    expect(repainted.sources.openmaptiles).toEqual({ type: "vector", url: "https://example.com/planet" });
    expect(repainted.sources.extra).toEqual(style.sources.extra);
  });

  it("does not change the style it was given", () => {
    expect((style.layers[0]?.paint as Record<string, unknown>)["background-color"]).toBe("white");
    expect(style.sources.openmaptiles).toHaveProperty("attribution");
  });

  it("credits OpenFreeMap, OpenMapTiles and OpenStreetMap", () => {
    const text = ATTRIBUTION.replace(/<[^>]+>/g, "").replace("&copy;", "©");
    expect(text).toBe("OpenFreeMap © OpenMapTiles Data from OpenStreetMap");
  });
});
