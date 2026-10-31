# Londoño Gómez scraper

Reviewed on 2026-10-30 (SPEC 04). Code: `src/sobreplano/infrastructure/scraping/londono_gomez.py` (`LondonoGomezSite`).

```
uv run --env-file .env python -m sobreplano.interface.cli.scrape londono-gomez
```

## Site

- Listing: `https://londonogomez.com/proyectos-vivienda`. All cards are in the initial HTML (62 on 2026-10-30), with no pagination and no JavaScript needed, so the scraper uses `httpx`, not Playwright.
- `www.londonogomez.com` redirects (301) to `londonogomez.com`.
- Each card links to `/node/{N}`, which redirects (301) to the canonical project page `/proyectos-vivienda/antioquia/{municipality}/{slug}`. One request per project: the canonical URL is read from the page's `<link rel="canonical">`.

## robots.txt

`https://londonogomez.com/robots.txt` allows everything except `/core/`, `/profiles/`, `/admin/`, `/search/`, `/user/…`, `/node/add/`, `/comment/reply/`, `/filter/tips` and `/media/oembed`. The listing, `/node/{N}` and the project pages are allowed. The fetcher checks robots.txt against the requested URL and again against the final URL after redirects.

## Selectors

| What | Where |
| --- | --- |
| Card | `.view-busqueda-proyectos .views-row` |
| Card link | `a[href^="/node/"]` |
| Card title | `.views-field-title` |
| Card type | `.views-field-field-tipo-de-proyecto` (`Vivienda`, `Lotes`, `Oficinas`, `Hotel`) |
| Card municipality | `.views-field-nothing` (`Medellín`, `La Estrella`, …) |
| Canonical URL | `link[rel="canonical"]` |
| Coordinates | `a[href*="/maps/dir/"]`, `google.com/maps/dir//{lat},{lon}/@…`, latitude first |
| Unit types | `.detail-apartment` with `h4` (name) and `span.price-apartament-types` (price); read by the LLM from the clean text, not by selector |

## Filters

Before fetching a project page, from the card: skip titles with "outlet" or "prueba", types other than `Vivienda`, and municipalities outside `Municipality`.

After fetching, from the canonical URL: keep only `/proyectos-vivienda/antioquia/{municipality}/{slug}` with the municipality in `Municipality` and no "outlet" in the slug. A page dropped here is not stored, not extracted and not recorded in `scraped_pages`; it only counts as "out of scope" in the summary.

## First full run (2026-10-30)

| | |
| --- | --- |
| Cards after the card filters | 25 |
| Pages fetched and stored | 21 |
| Out of scope after fetching | 3 (MAZZI, Ventto del Río, River Park) |
| Failed | 1 (Ezzenti: no Google Maps directions link) |
| Projects | 21 in 5 municipalities (Medellín 13, Bello 5, Sabaneta, Envigado, La Estrella) |
| Unit types | 45 valid, 32 rejected (almost all "no price": "PLANTA TÍPICA" blocks and projects that publish no prices) |
| Observations | 44, in 12 projects |
| Tokens (`openai:gpt-6-luna`) | 31,687 input, 3,821 output, about 0.005 USD |

## Known gaps

- **MAZZI, Ventto del Río and River Park** are housing cards in Medellín, but their canonical URL does not match the expected pattern. Their HTML is not stored (out of scope), so the reason is still unknown; check their canonical by hand on the next visit.
- **Ezzenti** has no Google Maps directions link, so it has no coordinates and fails every run.
- **9 projects have no price** on the site ("Desde" with no amount). They are created in the catalog but have no observations.
