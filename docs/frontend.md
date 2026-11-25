# Frontend (SPEC 11a)

The site in `web/`: a static Astro 7 site with one React island, built from the read API. Its design rules (tokens, contrast, what CI rejects) are in [`web/DESIGN.md`](../web/DESIGN.md).

## How it gets its data

```text
pnpm build
  -> GET /projects, 50 at a time until total      (SOBREPLANO_API_URL, at build time)
  -> one HTML page per project, og:image per project, sitemap
browser, on a project page
  -> GET /projects/{slug} when the chart comes into view   (PUBLIC_API_URL, CORS)
```

The price history is never written into the HTML. Only the browser asks for it, so the API's per-client limit protects it (40 detail requests a day per IP, SPEC 10). The island gets only the slug. It never retries a `429` or a `404`, and never refetches when the tab regains focus.

| Variable | Used by | Example |
| --- | --- | --- |
| `SOBREPLANO_API_URL` | The build (server side only). Without it the build fails instead of publishing an empty catalog | `http://localhost:8000` |
| `PUBLIC_API_URL` | The browser (history chart), and the CSP's `connect-src` | `http://localhost:8000` |
| `PUBLIC_SITE_URL` | Canonical URLs, `og:image`, sitemap, `robots.txt`. Defaults to `http://localhost:4321` until SPEC 12 sets the domain | `http://localhost:4321` |
| `E2E_PORT` | Playwright's preview, when 4321 is taken | `4401` |
| `CORS_ALLOWED_ORIGINS` (API) | Lets the site's origin read the API. A JSON list, in single quotes in `.env`, because uv drops bare inner quotes | `'["http://localhost:4321"]'` |

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
| `pnpm --dir web test` | Vitest: formats, view model, history, catalog coverage, contrast pairs, design rules, icons |
| `pnpm --dir web rules` | Colors, radii, shadows and fonts outside the tokens fail, with file and line |
| `pnpm --dir web tokens` | Regenerates `src/styles/tokens.css`; CI fails if it changes |
| `uv run python -m sobreplano.interface.cli.export_openapi` then `pnpm --dir web api:types` | After any API change: the contract and its TypeScript types. `test_openapi_snapshot.py` fails until the contract is exported |
| `pnpm --dir web e2e` | Playwright against the build (API running): axe at 390 and 1440 px, no horizontal scroll at 320 px, the `429` and `500` states, the keyboard, no CSP errors |
| `pnpm --dir web lhci` | Lighthouse CI on `/`, `/proyectos/` and one project page, mobile, with the budgets in `web/lighthouserc.json` |

## Screenshots

The reference screenshots (`web/tests/e2e/visual.spec.ts-snapshots/`) are made and compared only on Linux, in the official Playwright image, because fonts render differently on each system. On macOS the visual tests are skipped. They are also skipped without the kit (`web/kit`), because they show its icons.

To update them after an intended change, run the build and the comparison in the image. Use a separate `node_modules` volume (the Mac one has macOS binaries), with the API above running on the host:

```bash
docker run --rm -v "$PWD:/work" -v sobreplano-web-node-modules:/work/web/node_modules -w /work/web \
  -e CI=1 -e SOBREPLANO_API_URL=http://host.docker.internal:8000 -e PUBLIC_API_URL=http://host.docker.internal:8000 \
  mcr.microsoft.com/playwright:v1.65.1-noble \
  bash -c 'npm i -g pnpm@12.23.0 && pnpm install --frozen-lockfile --store-dir /tmp/pnpm-store && pnpm build && node_modules/.bin/playwright test visual --update-snapshots'
```

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
