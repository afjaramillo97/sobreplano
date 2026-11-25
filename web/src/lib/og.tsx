/**
 * The og:image of a project: a 1200×630 PNG drawn at build time with satori and resvg, on the
 * kit's lavender hero background. Colors come from the tokens, never written here.
 */
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { join } from "node:path";
import { Resvg } from "@resvg/resvg-js";
import satori from "satori";

import { flatten, indexTokens, resolve } from "../../scripts/build-tokens.mjs";
import tree from "../../tokens/sobreplano.tokens.json";
import { formatChange, formatDate, formatMillions } from "./format";
import { MUNICIPALITY_NAMES, type ProjectView } from "./projects";

export const OG_WIDTH = 1200;
export const OG_HEIGHT = 630;
const MARGIN = 72;

const tokens = indexTokens(flatten(tree));
const color = (path: string) => resolve(`{color.${path}}`, tokens) as string;

// satori reads WOFF, not WOFF2, so the static weights of @fontsource/plus-jakarta-sans.
// Resolved from web/, where the build runs, because the bundled page moves away from src/.
const require = createRequire(join(process.cwd(), "package.json"));
let fonts: Promise<{ name: string; data: Buffer; weight: 700 | 800; style: "normal" }[]> | undefined;

function loadFonts() {
  fonts ??= Promise.all(
    ([700, 800] as const).map(async (weight) => ({
      name: "Plus Jakarta Sans",
      data: await readFile(
        require.resolve(`@fontsource/plus-jakarta-sans/files/plus-jakarta-sans-latin-${weight}-normal.woff`),
      ),
      weight,
      style: "normal" as const,
    })),
  );
  return fonts;
}

/** The PNG of a project's og:image. */
export async function renderOgImage(project: ProjectView): Promise<Uint8Array<ArrayBuffer>> {
  const { from } = project;
  const place = [MUNICIPALITY_NAMES[project.municipality], project.neighborhood]
    .filter(Boolean)
    .join(", ");
  const svg = await satori(
    <div
      style={{
        width: OG_WIDTH,
        height: OG_HEIGHT,
        display: "flex",
        backgroundImage: `linear-gradient(180deg, ${color("primitive.hero.nav")}, ${color("primitive.hero.mid")})`,
        fontFamily: "Plus Jakarta Sans",
        color: color("text.primary"),
      }}
    >
      {/* satori adds padding to the size, so a fixed inner box keeps the 72 px margins. */}
      <div
        style={{
          width: OG_WIDTH - 2 * MARGIN,
          height: OG_HEIGHT - 2 * MARGIN,
          marginLeft: MARGIN,
          marginTop: MARGIN,
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
        }}
      >
      <div style={{ display: "flex", fontSize: 32, fontWeight: 800, color: color("text.heading-alt") }}>
        Sobreplano
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <div style={{ display: "flex", fontSize: project.name.length > 30 ? 56 : 72, fontWeight: 800, lineHeight: 1.15 }}>
          {project.name}
        </div>
        <div style={{ display: "flex", fontSize: 30, fontWeight: 700, color: color("text.secondary") }}>
          {`${project.developer.name} · ${place}`}
        </div>
      </div>
      {from?.priceCop != null && from.observedOn ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 24 }}>
            <div style={{ display: "flex", fontSize: 52, fontWeight: 800, letterSpacing: -1, color: color("text.price") }}>
              {`Desde ${formatMillions(from.priceCop)}`}
            </div>
            {from.changePct != null && (
              <div
                style={{
                  display: "flex",
                  padding: "8px 16px",
                  borderRadius: 4,
                  fontSize: 24,
                  fontWeight: 800,
                  backgroundColor: color("change.bg"),
                  color: color("change.text"),
                }}
              >
                {formatChange(from.changePct).toUpperCase()}
              </div>
            )}
          </div>
          <div style={{ display: "flex", fontSize: 26, fontWeight: 700, color: color("text.secondary") }}>
            {`${from.name}, precio observado el ${formatDate(from.observedOn)}`}
          </div>
        </div>
      ) : (
        <div style={{ display: "flex", fontSize: 44, fontWeight: 800, color: color("text.secondary") }}>
          Sin precio publicado
        </div>
      )}
      </div>
    </div>,
    { width: OG_WIDTH, height: OG_HEIGHT, fonts: await loadFonts() },
  );
  // A copy on its own ArrayBuffer, which is what a Response body accepts.
  return new Uint8Array(new Resvg(svg, { fitTo: { mode: "width", value: OG_WIDTH } }).render().asPng());
}
