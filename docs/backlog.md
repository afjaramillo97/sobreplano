# Backlog

Ideas raised while implementing a spec but left out of its scope. Each one goes into its own spec
when it is picked up.

## Versioned prompts (candidate: SPEC 09)

Raised during SPEC 08 (2026-11-13).

- Move every prompt to one folder inside the package, `src/sobreplano/infrastructure/llm/prompts/`
  (one file per prompt, e.g. `extractor.md`, `advisor_system.md`), with a loader that returns the
  text and its version (first 12 characters of its sha256). Inside `src/`, because the Lambda
  image only copies `src/sobreplano`.
- Record the prompt version with every LLM call: `prompt_version` in `llm_usage` and in
  `page_extractions` (needs a migration).
- Add the extractor prompt's version to the reuse key of `page_extractions` (today
  `text_sha256` + `model`): otherwise a changed extraction prompt keeps reusing extractions made
  with the old one.
- Keep the files in the repo (reviewed in PRs, no network, no cost) rather than Langfuse prompt
  management; they can be synced to Langfuse later.
- Pays off with the golden set and the judge of SPEC 09, which can then compare prompt versions,
  not only models.

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
