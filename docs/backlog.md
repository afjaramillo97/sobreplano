# Backlog

Ideas raised while implementing a spec but left out of its scope. Each one goes into its own spec
when it is picked up.

## Floor plan analysis with vision

Raised during SPEC 09 (2026-11-13), reviewing the extraction golden set.

- The extractor only reads the page text. Some rooms appear only on the floor plan images:
  Acento's 100.65 m² plan (Constructora Capital) shows 3 bathrooms, its text lists 2 (see
  `docs/scrapers/constructora-capital.md`).
- Idea: read each unit type's plan with a vision model to get bathrooms, bedrooms and a study,
  reusing the analysis by the image's hash (plans rarely change, so after the first pass it costs
  almost nothing).
- Rough cost of a full pass: about 250 plans, 1,000 to 2,000 input tokens each at high detail
  (to be measured), so 0.03 to 0.05 USD with `gpt-6-luna`, 0.25 to 0.50 USD with `gpt-6.1-terra`.
- The real work is elsewhere: finding each site's plan URLs and matching them to unit types
  ("APTO TIPO 6" on the plan, "Planta Apartamento 100.65 m2" in the text, joined by area),
  extra image requests within the scraper rules (robots.txt, one visit per site per day, raw
  images in S3), deciding what wins when text and plan disagree, and a vision golden set to
  check that rendered plans are counted right.

## Stabilize unit type names

Raised during SPEC 09 (2026-11-14), comparing extraction models.

- Constructora Capital names its unit types "Planta Apartamento 48.40 m2 Área Total". Models
  do not copy that name the same way every time: Luna returned "Planta Apartamento 48.40 m2",
  "Apartamento 48.40 m2" or the full name, sometimes differently between two runs of the same
  page (18 unit types renamed between 2 runs; Qwen3.7-Flash: 6). The extraction evals pair them
  by area for that reason (`pair_unit_types`) and report the exact-name rate (Luna 69 %,
  Qwen 85 %) and the renamed-between-runs list, without a threshold.
- Production already survives a rename: `_unit_types` in
  `src/sobreplano/application/scrape_developer.py:322-349` matches a stored unit type by
  normalized name (`normalize_unit_type_name`, `domain/scraping.py:194`), else by area when
  exactly one stored unit type has it (`_by_area`, `unit_types_with_same_area`,
  `domain/scraping.py:230`, areas equal to 2 decimals), else it creates a new one. The unique
  key is `(project_id, name)` (`infrastructure/db/models.py:121`).
- Read-only check on Supabase cloud (113 unit types, 49 projects): no history was split by a
  rename. 11 pairs of unit types in the same project share an area. In 10 of them both
  have the same observation dates, so they are distinct unit types (towers, types A/B), not
  one renamed. The exception is `reserva-de-los-bosques`: "Apto 181 M2 Tipo B" and the two
  "Apto 188 M2" types (A and B) have 4 observations each, from 2026-10-30 to 2026-11-02, while
  "Apto 181 M2 Tipo A" continues to 2026-11-14 (16 observations). They stopped being listed;
  none began afterwards, so nothing indicates a rename.
- Risks left: (a) a unit type whose area is shared with another one of the same project is
  never matched by area, so a rename of it creates a new unit type and cuts its history;
  (b) a rename together with an area change creates a new one; (c) the eval pairs areas
  within 0.05 m² and production within 0.01, so a model can look right in the eval and still
  create a new unit type.
- Possible fixes, for a spec of their own: tell the extractor to copy the unit type name
  exactly as the page writes it and measure it with the exact-name metric; or give each unit
  type a stable key built from the areas, and keep the name as a label.

## Counting rules in the extractor prompt, and a new measurement

Raised during SPEC 09 (2026-11-14), comparing Luna and Qwen3.7-Flash on the extraction golden set.

- The extractor prompt does not say how to count bedrooms and bathrooms when a page only lists
  rooms (Constructora Capital). The golden set follows rules (bedrooms: listed rooms, without
  service room, study or library; bathrooms: each "con baño" + "baño social" + service
  bathroom; no number published: count the listed rooms, else `None`) written in
  `docs/evals.md`. Put the same rules in `prompts/extractor.md` (it changes the prompt version
  and the reuse key, so pages are re-extracted once).
- Measure again on the same golden set, with the same 2 runs per page, three variants: Luna,
  Qwen3.7-Flash with reasoning off (as now) and Qwen3.7-Flash with reasoning on. Compare field
  accuracy, cost per page and latency. The first measurement left Qwen at 90.3 % field accuracy
  with reasoning off.
- Keep the labels honest: before measuring, someone other than the first reader of the
  pages (the labels started from Luna's extractions) re-reads a sample of the room counts.

