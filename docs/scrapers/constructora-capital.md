# Constructora Capital scraper

Reviewed on 2026-11-02 (SPEC 06, step 1) by downloading the listing and two project pages once with `HttpFetcher` (project user-agent, robots.txt, 2 s delay) into `data/raw/explore/` (git-ignored). Code: `src/sobreplano/infrastructure/scraping/constructora_capital.py` (`ConstructoraCapitalSite`, step 6).

## Site

- Listing: `https://www.constructoracapital.com/proyectos/1/medellin-y-alrededores`. All cards are in the server HTML (33 on 2026-11-02), with no pagination and no JavaScript needed, so the scraper uses `httpx`, not Playwright.
- Project page: `/proyecto/1/medellin-y-alrededores/{zone}/{id}/{slug}`, linked from the card with a relative `href` (no leading `/`). No redirect: the requested URL is the canonical URL (`<link rel="canonical">` matches it on Axis and Acento).
- The zone is not always the municipality: it is sometimes a neighborhood (`ciudad-del-rio`, `santa-ana`, `niquia`, `camino-verde`, `tierra-firme`, `loma-del-escobero`, …). See "Zones" below.
- The page has no `<header>`, `<nav>` or `<footer>` tags: page chrome lives in `div#header`, `div#footer`, `div#postfooter` and `div.contactos_barra`, so the generic `clean_text` lets the whole menu through. The Capital parser removes those blocks by id/class.

## robots.txt

`https://www.constructoracapital.com/robots.txt` is `User-agent: *` with no `Disallow`, plus a `Sitemap` line. Everything is allowed.

## Selectors

| What | Where |
| --- | --- |
| Card | `ul.grid_proyectos > li` (class `inventario_si` or `inventario_no`, the latter for sold-out projects) |
| Card link | `a[href]` matching `proyecto/1/medellin-y-alrededores/{zone}/{id}/{slug}` (relative) |
| Card type | `p.tipo` (`APARTAMENTOS`, `OFICINAS`) |
| Card zone label | `h2.subrayado strong` (`Envigado`, `Ciudad del Río`, `Rionegro - Los Colegios`, …) |
| Card price | `p.precio` (`Desde $710,200,000`, or `Éxito en Ventas. Totalmente vendido.`) |
| Canonical URL | `link[rel="canonical"]` |
| Coordinates | `a[href*="google.com.co/maps/place/"]`: `maps/place/{lat}+{lon}/@{lat},{lon},17z`, latitude first |
| Waze link | `waze.com/{lang}/live-map/directions/co/antioquia/{municipality}/{name or address}?to=place.{google_place_id}`: a place id, **no coordinates** |
| Project sections | `div#p_presentacion`, `#p_ciudadela`, `#p_plantas`, `#p_urbanismo`, `#p_avances`, `#p_especificaciones`, `#p_contacto`, `#p_otrosproyectos`, each with a `…_tit` title block |
| Unit type (floor plan) | inside `#p_plantas`: `p.destacado.torre` (name, "Planta Apartamento 60.01 m2 Área Total"), `p.precio` (`$ 710,200,000`) or `p.enDolares` ("Consultar precios y disponibilidad con Sala de Ventas"), `p.destacado` (`ÁREA TOTAL: 60.01 m2`), next `p` (`ÁREA PRIVADA: 54.06 m2`, sometimes with no unit: `ÁREA PRIVADA: 64.32`). Read by the LLM from the clean text, not by selector |
| Construction progress | `div#p_avances_tit` and `div#p_avances` ("ULTIMA PUBLICACIÓN Octubre 2026", a YouTube iframe): changes monthly, removed from the clean text |
| Other projects | `div#p_otrosproyectos_tit` and `div#p_otrosproyectos` ("TAMBIÉN PUEDEN INTERESARTE / OTROS PROYECTOS"): cards of **other** projects with their own zone and "Desde" price. **The cards change on every request**: two loads of Verde Olivo on 2026-11-02 showed Bambú (Itagüí) and Nature Aqua (Sabaneta), then Bosque Rosa (Rionegro), Urbanity Office and Nature Bio (Sabaneta). Axis had the block in the downloaded HTML, Acento did not |

## What the pages contain (Axis and Acento, 2026-11-02)

- **Prices:** comma thousands separator (`$ 710,200,000`), each followed by a dollar reference (`(223,124 US)`). Footnotes about VIS prices in pesos, SMMLV and dollar prices repeat on every page.
- **Not only the cheapest unit has a price.** Acento: 1 of 5 floor plans has a price (78.46 m², $822,200,000), the rest say "Consultar precios…". Axis: 5 of 6 have a price ($710.2M to $1,079.7M); only 72.38 m² says "Consultar precios…".
- **Unit type names include the area** ("Planta Apartamento 60.01 m2 Área Total"). The seed names them "Tipo 04" etc. Axis matches the seed one to one by built area: 60.01 → Tipo 04, 60.67 → Tipo 02, 60.10 → Tipo 12, 85.86 → Tipo 06, 94.73 → Tipo 14. Acento 78.46 → Tipo 2.
- **Coordinates:** Axis and Acento share `6.171977710068938,-75.59416941716492` (Ciudad Peldar). They appear only inside the Google Maps `place` link (`/maps/place/{lat}+{lon}/@{lat},{lon},17z`); there is no loose `lat,lon` outside a link. The seed has `6.1735` / `6.172` (hand-entered).

## Zones (all 33 cards on 2026-11-02)

| Zone in URL | Cards | Municipality | Note |
| --- | --- | --- | --- |
| `envigado` | 4 | `ENVIGADO` | Axis, Murano, Acento, Artiko |
| `loma-del-escobero` | 1 | `ENVIGADO` | Artesia |
| `itagui` | 4 | `ITAGUI` | |
| `bello` | 4 | `BELLO` | |
| `santa-ana` | 2 | `BELLO` | |
| `bello-santa-ana` | 1 | `BELLO` | |
| `niquia` | 1 | `BELLO` | |
| `sabaneta` | 2 | `SABANETA` | |
| `la-estrella` | 1 | `LA_ESTRELLA` | |
| `ciudad-del-rio` | 2 | `MEDELLIN` | |
| `guayabal-las-villas` | 1 | `MEDELLIN` | sold out |
| `san-antonio-de-prado` | 1 | `MEDELLIN` | |
| `robledo-pajarito` | 1 | `MEDELLIN` | |
| `camino-verde` | 2 | `ENVIGADO` | Verde Olivo, Verde Silvestre. Checked on Verde Olivo (2026-11-02): Google Maps `6.154604,-75.578111`, Waze path `antioquia/envigado/…` ("Zona 6, Envigado"), text "En Envigado…", sales room Calle 39 D Sur # 25 - 36 |
| `tierra-firme` | 1 | — | Turquesa, sold out: discarded by slug (`SKIPPED_SLUGS`, owner's decision, 2026-11-02); the zone stays out of the table, so a new project there warns |
| `santa-fe` | 2 | — | Urbanity Office and Urbanity Renta Selecta: skipped by the slug words `office` and `renta`; a new housing project there warns |
| `rionegro-los-colegios` | 3 | — | Monte Rosa, Valle Rosa, Bosque Rosa: outside the Aburrá Valley, skipped |

## Filters

Before fetching a project page, from the card URL, and again on the canonical URL after fetching: skip zones starting with `rionegro`, slugs in `SKIPPED_SLUGS` (`turquesa`) and slugs with `office` or `renta`. Any other zone not in `CAPITAL_ZONES` skips the card with a warning in the log; add it to the table after checking the project's location (map, Waze path, sales room address). On 2026-11-02 this leaves 27 of the 33 cards.

Sold-out projects (`inventario_no`) are not filtered: they enter the catalog without prices.

## Slugs

Project slugs get the prefix `capital-` (`capital-verde-olivo`): slugs are unique across developers and Capital's are short. Only the slug changes; the name users see is the one the model extracts. The three seed projects keep their slugs (`axis-ciudad-peldar`, …) and are found by `source_url`.

## Clean text

Removed before the text is built: `#header`, `#footer`, `#postfooter`, `.contactos_barra` (page chrome, since the site has no `<header>`/`<nav>`/`<footer>` tags), `#p_avances_tit` and `#p_avances` (construction progress, changes monthly) and `#p_otrosproyectos_tit` and `#p_otrosproyectos` (other projects' cards, different on every request and with their own prices). Axis goes from about 12,600 to 9,700 characters. The dollar reference next to each price, `p.enDolares` with `(139,820 US)`, is removed too: it follows the exchange rate, so on 2026-11-04 it changed the clean text of all 27 pages and nothing was reused. The `p.enDolares` that says "Consultar precios y disponibilidad con Sala de Ventas" stays, because it tells the model the floor plan has no price.

## First local run (2026-11-02, local database)

```
uv run --env-file .env python -m sobreplano.interface.cli.scrape constructora-capital --limit 2 --dry-run
uv run --env-file .env python -m sobreplano.interface.cli.scrape constructora-capital
```

| | |
| --- | --- |
| Pages listed and fetched | 27 of 27, 0 out of scope, 0 failed |
| Projects | 24 added, plus the 3 seed projects (Axis, Murano, Acento) found by `source_url` |
| Unit types | 59 valid, 33 rejected (almost all "no price": "Consultar precios…" and sold-out projects), 51 added |
| Seed unit types matched by area | 8: Axis Tipo 02/04/06/12/14, Murano Apto 02/09, Acento Tipo 2 |
| Observations | 59 |
| Projects without location | 0 |
| Tokens (`openai:gpt-6-luna`) | 74,904 input, 5,257 output, about 0.010 USD (dry run of 2 pages: 0.0007 USD) |

Checks on the local database after the run: `slug like '%ciudad-peldar%'` gives 3 projects; `slug ilike '%rosa%' or '%urbanity%'` gives 0; every Axis seed unit type has 2 observations (manual on 2026-10-28, scraper on 2026-11-02, same price).

**Raw HTML is not stable, the clean text is.** Velvet and Villa Vento were downloaded twice (dry run and real run): the raw HTML hash differed both times, the clean text from `ConstructoraCapitalSite` was identical. With the generic `clean_text` alone (other projects' cards left in) the text differed too, which confirms that `#p_otrosproyectos` has to go.

**The model names the same floor plan differently across pages** ("Apartamento 60.01 m2" on Axis, "Planta Apartamento 67.41 m2 Área Total" on Murano). Within a project this is stable as long as the clean text does not change (the extraction is reused), and the seed rows were matched by area anyway.

The seed's hand-entered coordinates (6.1735, -75.5925 for Axis) differ from the page's (6.1719777, -75.5941694): logged as "location changed", not overwritten.

## Not done in step 1

- Murano's page was not downloaded (not needed for the selectors; its seed unit types are matched in step 5).
