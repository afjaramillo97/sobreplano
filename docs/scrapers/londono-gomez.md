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

## What changes in the HTML from day to day (SPEC 06, step 1)

Primavela on 2026-10-30 and 2026-10-31: same size (145,075 bytes), 14 changed lines, all of them Drupal per-request tokens:

- `form_build_id` (and its `data-drupal-selector`) of the 3 forms on the page.
- `honeypot_time` of the same 3 forms.
- The `js-view-dom-id-…` class of the `view-oficinas` block.

All of them live inside `<form>` or in attributes, which `clean_text` already drops. Over the 21 pages stored on both days, the raw HTML hash differs every day and the `clean_text` hash is identical for all 21 (Graz del Río and M Living were stored twice on 2026-10-30, also with the same text). So the clean text is a stable reuse key and `clean_text` needs no change.

The same check on the HTML the Lambda stored in S3 on 2026-11-01 and 2026-11-02 gives the same result: 21 of 21 pages with identical clean text, the same 14 token lines changed in Primavela, and the same clean-text hashes as on 2026-10-30 and 2026-10-31, so the text was stable over four days.

Ezzenti (`/node/203631` → `/proyectos-vivienda/antioquia/medellin/ezzenti`, downloaded once on 2026-11-02): no Google Maps link, no Waze link, and its map script has empty coordinates (`parseFloat(parseFloat().toFixed(7))`). The page does say it is in Calasanz, Medellín. No point is inferred from that: since SPEC 06 the project is stored without coordinates (`location` NULL, a warning in the log) instead of failing, and the scraper stores the point the day the developer publishes its map. A point can also be added by hand to `MANUAL_LOCATIONS` (`src/sobreplano/infrastructure/scraping/manual_locations.py`).

## Known gaps

- **MAZZI, Ventto del Río and River Park** are housing cards in Medellín, but their canonical URL does not match the expected pattern. Their HTML is not stored (out of scope), so the reason is still unknown; check their canonical by hand on the next visit.
- **Ezzenti** publishes no map, so it is stored without coordinates (since SPEC 06; before, it failed every run).
- **9 projects have no price** on the site ("Desde" with no amount). They are created in the catalog but have no observations.
