# Frontend (SPEC 11a, 11b, 11c, 11d)

The site in `web/`: a static Astro 7 site with React islands (the price history, the search, the advisor, the calculator, "¿Me alcanza?" and the comparison), built from the read API. Its design rules (tokens, contrast, what CI rejects) are in [`web/DESIGN.md`](../web/DESIGN.md).

## How it gets its data

```text
pnpm build
  -> GET /projects, 50 at a time until total      (SOBREPLANO_API_URL, at build time)
  -> one HTML page per project, og:image per project, sitemap
  -> datos.gov.co, only with REFERENCE_RATE=live           (the bank rate, SPEC 11d)
browser, on a project page
  -> GET /projects/{slug} when the chart comes into view   (PUBLIC_API_URL, CORS)
browser, on /proyectos/ (SPEC 11b)
  -> nothing from the API: the catalog comes inside the page and is filtered in memory
  -> tiles.openfreemap.org, only while the map is shown    (style, tiles, fonts, sprites)
```

The price history is never written into the HTML. Only the browser asks for it, so the API's per-client limit protects it (40 detail requests a day per IP, SPEC 10). The island gets only the slug. It never retries a `429` or a `404`, and never refetches when the tab regains focus.

| Variable | Used by | Example |
| --- | --- | --- |
| `SOBREPLANO_API_URL` | The build (server side only). Without it the build fails instead of publishing an empty catalog | `http://localhost:8000` |
| `PUBLIC_API_URL` | The browser (history chart and advisor), and the CSP's `connect-src` | `http://localhost:8000` |
| `PUBLIC_SITE_URL` | Canonical URLs, `og:image`, sitemap, `robots.txt`. Defaults to `http://localhost:4321` until SPEC 12 sets the domain | `http://localhost:4321` |
| `REFERENCE_RATE` | The build. `live` reads the bank rate from datos.gov.co; unset (CI, tests) uses the versioned file. The deployment (SPEC 12) must set it | `live` |
| `E2E_PORT` | Playwright's preview, when 4321 is taken | `4401` |
| `CORS_ALLOWED_ORIGINS` (API) | Lets the site's origin read the API. A JSON list, in single quotes in `.env`, because uv drops bare inner quotes | `'["http://localhost:4321"]'` |

## The search (SPEC 11b)

`/proyectos/` is one island (`web/src/components/search/SearchPage.tsx`, `client:load`). The build hands it every project as a `SearchItem` (`web/src/lib/search.ts`): only what the cards show, never the history. Its server render is the whole catalog without filters, so the page works and is indexed without JavaScript; the filter controls show only with JavaScript.

All the logic is pure and tested in `web/tests/unit/search.test.ts`: the URL, matching (every unit filter on the same unit type), the "desde" with filters (the cheapest unit type that passes), the four orders, the map bounds and the price histogram. It never calls `GET /projects`: the API allows 30 lists a minute per IP, which moving the map would use up. Reconsider it past about a thousand projects.

### The URL

Every filter lives in the URL, in this order, with default values left out, so one search always gives one URL. `parseSearch` never throws: an invalid value is ignored and drops out on the next write.

| Parameter | Example | Rule |
| --- | --- | --- |
| `q` | `q=ditaires` | Free text, up to 80 characters; name, neighborhood, municipality or developer, without accents |
| `municipio` | `municipio=itagui,envigado` | `Municipality` slugs, comma separated |
| `constructora` | `constructora=ceiba-urbana` | A developer slug of the catalog |
| `precio_min`, `precio_max` | `precio_max=400000000` | Pesos, whole numbers |
| `alcobas`, `banos` | `alcobas=2` | Minimums, 1 to 5 |
| `area_min`, `area_max` | `area_min=50` | Whole m² |
| `orden` | `orden=subida` | `precio` (default), `precio_desc`, `subida`, `nombre` |
| `mapa` | `mapa=6.1725,-75.6130,12.5` | Latitude and longitude with 4 decimals, zoom with 1 |
| `mover` | `mover=0` | Only while "Buscar al mover el mapa" is off |
| `vista` | `vista=mapa` | Only in the phone's map view (below 1024 px) |

Filters and order replace the history entry, so "Atrás" leaves the search in one step; typing, sliders and the map write after 250 ms (Safari throws after 100 history writes in 30 s). Only the phone's map view pushes an entry, so "Atrás" goes back to the list. The home page's search is a plain `GET` form to `/proyectos/` with `municipio` and `precio_max`.

### The map

`web/src/components/search/ResultsMap.tsx`, loaded with `import()` only when it is shown: from 1024 px beside the list, and below that after "Ver mapa". MapLibre GL JS 6 on OpenFreeMap's Positron (`STYLE_URL` in `web/src/lib/map-style.ts`), with land, parks and water repainted from the `map.*` tokens. Each project with coordinates is an HTML `<button>` pill; Supercluster groups pills closer than 72 px. MapLibre's worker is served from the site (`setWorkerUrl`), so the CSP needs `worker-src 'self'` and no `blob:` worker.

From 1024 px, with "Buscar al mover el mapa" on, the list shows the projects inside the map, and those without coordinates go last under "Sin ubicación publicada". If the style or the tiles fail, or there is no WebGL, the panel says "No pudimos cargar el mapa. La lista sigue funcionando." and the list stops filtering by zone.

JavaScript budget, gzip: the first load of `/proyectos/` is about 103 KB (120 at most; the popovers and the "Más filtros" panel load on first use), the map chunk about 297 KB (320 at most) plus MapLibre's worker, about 157 KB, which runs off the main thread.

**Plan B for the tiles.** OpenFreeMap is run by one person, with no service agreement. If it goes away, cut a PMTiles file of the Aburrá Valley from the OpenMapTiles planet, put it in Cloudflare R2 (free egress), serve the same Positron style from the site pointing at it, and change only `STYLE_URL` and the CSP's map origin.

### Testing without the network

`web/tests/e2e/fixtures.ts` answers every request to `tiles.openfreemap.org` with `web/tests/fixtures/map-style.json` (land only, no tiles, fonts or sprites) and aborts the rest, so no test and no screenshot depends on the network. A test that wants the map down routes the same host to a `503`. The fictitious catalog has two projects about 240 m apart in Itagüí, to test the groups.

## The advisor (SPEC 11c)

`/asesor/` is one island (`web/src/components/advisor/AdvisorPage.tsx`, `client:load`), after the kit's *Message* screen. The build hands it the catalog as `SearchItem`s (for the small cards and the project in context) and the hosts of the developers' sites. The browser sends `POST /advisor/chat/stream` to `PUBLIC_API_URL` and reads the events with `fetch` and `eventsource-parser` (`web/src/lib/advisor/stream.ts`), one message at a time.

- **URL:** `c` (the `thread_id` of a stored conversation) and `proyecto` (a catalog slug, from the project page's "Pregúntale al asesor"); unknown values are ignored.
- **Storage:** `localStorage`, key `sobreplano.asesor.v1` (`web/src/lib/advisor/store.ts`): at most 30 conversations, deleted after 7 days without activity unless "Conservar mis conversaciones en este navegador" is on. Without storage (private mode, full quota) the page keeps the current conversation in memory and says so. A conversation the server no longer has (`404`) or that reached 20 messages (`409`) stays readable and is marked closed.
- **Links:** only project pages and the developers' hosts (`web/src/lib/advisor/links.ts`, see `docs/security.md`).
- **Errors:** the texts and actions of SPEC 11c §6 are in `web/src/lib/advisor/labels.ts`.
- **Weight:** the first load is about 110 KB gzip (150 at most); `react-markdown` and `remark-gfm` load with the first answer.

### Testing without the API

`web/tests/e2e/advisor.spec.ts` answers `POST /advisor/chat/stream` with fixed SSE bodies through `page.route`, so no test reaches the API or the model. The live steps need a body that arrives in parts, which `route.fulfill` cannot send, so that test swaps `fetch` with `addInitScript`. The tests wait for the island to hydrate before typing.

## Calculator, "¿Me alcanza?" and comparison (SPEC 11d)

Everything is computed in the browser: no API call, and income and savings never go in a request.

| Page | Island | What the build hands it |
| --- | --- | --- |
| `/calculadora/` | `finance/Calculator.tsx` (`client:load`) | The catalog as `SearchItem`s, to count what fits, and the reference rate |
| `/proyectos/{slug}/` | `finance/AffordabilityBlock.tsx` (`client:visible`) and `compare/CompareButton.tsx` (`client:idle`) | The "desde" price, its unit type and day, the rate |
| `/comparar/?p=a,b,c` | `compare/Comparison.tsx` (`client:load`) | `CompareItem`s (`lib/compare.ts`): current unit types with both areas, and the rate |

- **Maths:** `web/src/lib/finance.ts` is the port of `domain/finance.py` (decimals, never floats). `uv run python -m sobreplano.interface.cli.finance_vectors` writes what Python gives for fixed inputs to `web/tests/fixtures/finance-vectors.json`; `--check` fails CI if the file is stale. Change a formula in both places, then regenerate.
- **Calculator:** the max price never needs construction installments (the savings cover its down payment), so when the savings are the limit it also shows the price the income allows and what reaching it would take each month.
- **Comparison:** 2 to 4 projects, one area at a time (private or built, "No reportada" when missing, never estimated). The lowest price per m² is marked over every compared project. Price per m² rounds half to even, as the API does. Below 1024 px two columns show, each with a selector. In the local database (data up to 2 Nov 2026), 73 of 103 unit types report a private area (Constructora Capital 100 %, Londoño Gómez 32 %); all report a built one.
- **Selection:** the search's "Comparar" checkboxes and the project page's button. Opening `/comparar/?p=…` replaces the saved selection with the URL's; unknown and repeated slugs are ignored.

### Storage

| Key | What | Cleared by |
| --- | --- | --- |
| `sobreplano.finanzas.v1` (`lib/finances-store.ts`) | Income, savings, VIS or not, months, rate, term, down payment | "Olvidar mis datos" |
| `sobreplano.comparar.v1` (`lib/compare-store.ts`) | Up to 4 slugs | "Quitar todos" |

Without `localStorage` (private mode, full quota) the islands work in memory and say so.

### The reference rate

The average rate banks lent at for housing in the latest week, weighted by the amount disbursed, from the Superfinanciera's open data (dataset `qzsc-9esp`, format 414, weekly, CC BY-SA 4.0): VIS and not VIS, in pesos only. `web/src/lib/reference-rate.ts` queries it at build time when `REFERENCE_RATE=live` and falls back to `web/src/data/reference-rate.json` if the network fails or the answer does not pass (each rate 5 to 30 % EA and at least 50 loans, week under 45 days old).

To refresh the fallback, in a pull request: `pnpm --dir web rate:update`, then regenerate the screenshots. The 45-day limit applies to the live query only: an old versioned file is still used, and the cut-off date on the page is the only sign.

### JavaScript budget

`/calculadora/` and `/comparar/`: at most 90 KB gzip of initial JavaScript (89.5 kB and 85.8 kB when written; React alone is about 68). Their islands join classes with `cx`, not `cn` (tailwind-merge), import `button-variants.ts` rather than `button.tsx`, and use `finance/NativeSelect.tsx` instead of `ui/select.tsx`, whose icon brings every icon. CI does not check this budget.

## Running it locally

Node 24 and pnpm 12 through corepack (`corepack enable pnpm`, or `corepack pnpm …`). If `corepack enable` cannot write to `/usr/local/bin`, use `corepack enable --install-directory ~/.local/bin pnpm`.

The site is built and tested against the fictitious catalog (`web/tests/fixtures/catalog.json`), in a separate local database so the development data stays untouched:

```bash
supabase db start
# Recreate the sobreplano_web database, migrate it and load the fictitious catalog
uv run --env-file .env python -c "from pathlib import Path; from sobreplano.evals.advisor.database import prepare; print(prepare('postgresql+psycopg://postgres:postgres@127.0.0.1:54322/sobreplano_web', Path('web/tests/fixtures/catalog.json')))"
# The API on that database, without rate limits, open to the preview
DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:54322/sobreplano_web \
  RATE_LIMITS_ENABLED=false CORS_ALLOWED_ORIGINS='["http://localhost:4321"]' \
  uv run --env-file .env uvicorn sobreplano.interface.api.main:app --port 8000

pnpm --dir web install
SOBREPLANO_API_URL=http://localhost:8000 PUBLIC_API_URL=http://localhost:8000 pnpm --dir web build
pnpm --dir web preview          # http://localhost:4321
```

`pnpm --dir web dev` also works, with the same two variables.

## Checks

| Command | What |
| --- | --- |
| `pnpm --dir web check` | `astro check`: types, 0 errors and 0 warnings |
| `pnpm --dir web test` | Vitest: formats, view model, history, search, map style, catalog coverage, contrast pairs, design rules, icons, the finance port against Python's vectors, the reference rate, the browser stores and the comparison. No test reaches the network |
| `pnpm --dir web rate:update` | Rewrites the versioned reference rate from datos.gov.co (reaches the network) |
| `pnpm --dir web rules` | Colors, radii, shadows and fonts outside the tokens fail, with file and line |
| `pnpm --dir web tokens` | Regenerates `src/styles/tokens.css`; CI fails if it changes |
| `uv run python -m sobreplano.interface.cli.export_openapi` then `pnpm --dir web api:types` | After any API change: the contract and its TypeScript types. `test_openapi_snapshot.py` fails until the contract is exported |
| `pnpm --dir web e2e` | Playwright against the build (API running): axe at 390 and 1440 px (also with "Más filtros" open and on the phone's map view), no horizontal scroll at 320 px, the `429` and `500` states, the keyboard, no CSP errors, and the search (`search.spec.ts`: filters and their URL, the map, its pills and groups, the phone's map view, the page without JavaScript), plus the calculator and "¿Me alcanza?" (`finance.spec.ts`) and the comparison (`compare.spec.ts`). A test that clicks or types right after loading waits with `hydrated()` first |
| `pnpm --dir web lhci` | Lighthouse CI on `/`, `/proyectos/`, one project page, `/asesor/`, `/calculadora/` and `/comparar/`, mobile, with the budgets in `web/lighthouserc.json` |

## Screenshots

The reference screenshots (`web/tests/e2e/visual.spec.ts-snapshots/`) are made and compared only on Linux, in the official Playwright image, because fonts render differently on each system. On macOS the visual tests are skipped. They are also skipped without the kit (`web/kit`), because they show its icons.

To update them after an intended change, run the build and the comparison in the image. Use a separate `node_modules` volume (the Mac one has macOS binaries), with the API above running on the host:

```bash
docker run --rm -v "$PWD:/work" -v sobreplano-web-node-modules:/work/web/node_modules -w /work/web \
  -e CI=1 -e SOBREPLANO_API_URL=http://host.docker.internal:8000 -e PUBLIC_API_URL=http://host.docker.internal:8000 \
  mcr.microsoft.com/playwright:v1.65.1-noble \
  bash -c 'npm i -g pnpm@12.23.0 && pnpm install --frozen-lockfile --store-dir /tmp/pnpm-store && pnpm build && node_modules/.bin/playwright test visual --update-snapshots=all'
```

`all` matters: the comparison allows 1 % of different pixels, so a small change in a tall page passes and, without it, the old image stays.

Then look at every changed image before committing it, and put the matching kit screen beside it in the PR. The image's version must match `@playwright/test` in `web/package.json`. When Dependabot updates one, update the other (also in `.github/workflows/web.yml`) and make the screenshots again.

## CI

`.github/workflows/web.yml` runs on pull requests that touch `web/`, the API, or the workflow. It migrates and seeds the fictitious catalog, starts the API, then runs:
- the install and `pnpm audit`;
- the tokens and API types, which must stay unchanged;
- the design rules, `astro check`, Vitest and the build;
- Playwright in the official image;
- Lighthouse CI.

The kit is checked out with `KIT_REPO_TOKEN` (see [deploy.md](deploy.md#the-sites-private-kit-spec-11a)).

## The kit

Icons come from the private repository `sobreplano-kit`, mounted as the submodule `web/kit` (`git submodule update --init web/kit`, which needs access to it). Without it, `src/lib/icons.ts` falls back to our own drawings in `src/assets/icons-fallback/`, and the site still builds. Never copy kit files into this repository (UI8 license).
