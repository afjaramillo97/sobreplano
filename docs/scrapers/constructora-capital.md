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
| `tierra-firme` | 1 | — | Turquesa, sold out: discarded (owner's decision, 2026-11-02), not in the table |
| `santa-fe` | 2 | — | Urbanity Office and Urbanity Renta Selecta: skipped by title |
| `rionegro-los-colegios` | 3 | — | Monte Rosa, Valle Rosa, Bosque Rosa: outside the Aburrá Valley, skipped |

## Filters (step 6)

Before fetching a project page, from the card URL: skip Rionegro zones and slugs with `office` or `renta`. A zone not in the table skips the card with a warning in the log.

## Not done in step 1

- Murano's page was not downloaded (not needed for the selectors; its seed unit types are matched in step 5).
