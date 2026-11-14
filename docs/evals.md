# Evals (SPEC 09)

Numbers, not impressions: a golden set for the advisor, one for the extraction, and the model
choice each one supports. Reports are written to `evals/reports/` (git-ignored).

## Extraction golden set

16 pages of two developers (Londoño Gómez, Constructora Capital), labeled by hand. The scraped
text and the labels are **not** in the repo: they live in the private S3 bucket under
`evals/extraction/v1/` and in `.evals/` (git-ignored). `build` creates the labels from the
raw HTML, `pull` and `push` sync them.

```
uv run --env-file .env python -m sobreplano.evals.extraction run --model openai:gpt-6-luna --repeat 2
uv run --env-file .env python -m sobreplano.evals.extraction run --model openrouter:qwen/qwen3.7-flash --repeat 2
```

A model is eligible as the extractor if price accuracy ≥ 98 %, unit type recall ≥ 95 % and
field accuracy ≥ 95 %. Unit types are paired by exact name, then by area when the area is
unambiguous (see `pair_unit_types` and `specs/09-evals.md`).

### Result (2026-11-14, extractor prompt `6682e7fa8220`, 2 runs per page)

| | Luna (`openai:gpt-6-luna`) | Qwen3.7-Flash (`openrouter:qwen/qwen3.7-flash`) | Threshold |
| --- | --- | --- | --- |
| Price accuracy | 100 % (188/188) | 100 % (188/188) | ≥ 98 % |
| Unit type recall | 98.9 % (188/190) | 98.9 % (188/190) | ≥ 95 % |
| Field accuracy | 98.7 % | **90.3 %** | ≥ 95 % |
| Exact unit type name (of matched) | 69.1 % | 85.1 % | report only |
| Unit types renamed between runs | 18 | 6 | report only |
| Project name and neighborhood | 81.2 % | 62.5 % | report only |
| Perfect pages | 22/32 | 5/32 | |
| Cost, 32 calls | 0.0121 USD | 0.0043 USD | |
| Latency per page | 3.4 s | 4.5 s | |
| Eligible | **yes** | no | |

**Decision:** Luna stays as the extractor and the production prompt does not change in this
spec. Qwen3.7-Flash costs about a third of Luna per page, but the saving is cents a month and
does not justify another provider, and it fails the field threshold (see the cases below).
Changing the production model would be its own change, with a `terraform plan`.

### Counting rules of the golden set

The labels follow these rules, written down so that a model that counts differently is
measured against a stated criterion and not against a habit:

- **Bedrooms:** the bedrooms the page lists, not counting a service bedroom, a study or a
  library. A range ("2 o 3 alcobas") is the minimum.
- **Bathrooms:** each bedroom "con baño", plus the "baño social", plus the service bathroom.
- **No published number:** count the listed rooms; if that cannot be done, `None`.

On 2026-11-14 all 16 labels (95 unit types) were checked against these rules by script, with
no LLM: Constructora Capital by counting the listed rooms of each plan (42 unit types) and
Londoño Gómez by reading the published "N alcobas" / "N baños" of each type (53). **None
changed**, so the metrics above stand. Where Londoño Gómez publishes no counts (Atlántica
N, O, S and X, Parc Avignon 02 and 03 of tower 2, Primavela), the label is `None`. Costa Azul has no unit type in its label.
The Londoño Gómez check matches a type by name and accepts any of the blocks that share it
(Poblado Central and Verdeventura repeat names across towers), so it is a little looser there.

### Cases where Luna got every field and Qwen did not

12 page runs are like this (Bambú, Pinaria, Artiko, Velvet, Acento, Trópico, Parc Avignon).
Five of them:

| Page and unit type | What the text says | Label (= Luna) | Qwen |
| --- | --- | --- | --- |
| Parc Avignon, Tipo 04 tower 2 (202 m²) | "3 alcobas + Alcoba de servicio", "5 baños" | 3 bedrooms | **4** (counts the service room) |
| Bambú, plan 48.40 m² | "Habitación principal con vestier y baño", "Baño social" | 1 bedroom, 2 bathrooms | **`None` and `None`** |
| Pinaria, plan 70.52 m² | main bedroom "con baño", Habitación 2, Habitación 3, "Baño social" | 3 bedrooms, 2 bathrooms | bathrooms **`None`** (6 unit types of the page, both runs) |
| Acento, plan 69.13 m² | main bedroom "con baño", "Habitación 2 con baño", "Baño social" | 3 bathrooms | **2** (loses the bathroom of bedroom 2) |
| Artiko, plan 66.40 m² (run 2) | main bedroom "con baño", Habitación 2, Biblioteca, "Baño social" | 2 bedrooms, 2 bathrooms | **3** bedrooms (counts the library), bathrooms **`None`** |

Constructora Capital does not publish bedroom or bathroom numbers, only the list of rooms of
each plan, so a model has to count. Luna counts; Qwen often returns `None`, and sometimes
counts too much (service room, library) or too little (a bathroom inside a bedroom).

### Reservations about this comparison

1. **Qwen ran with reasoning off** (`reasoning: {enabled: false}`), as the production
   extractor does for Luna, to keep the cost comparable. Counting rooms is the kind of task
   where reasoning may help, so the result says nothing about Qwen with reasoning on.
2. **The first draft of the labels came from Luna.** `build` started from the extractions
   stored in the cloud database, made by Luna, and the labels were then corrected by hand
   (names, neighborhoods, bathrooms of Verde Olivo, among others). The corrections were
   independent, but the first reading of every page was Luna's, which favors it on the
   fields counted from rooms. The check against the counting rules above reduces this risk
   without removing it.

Also, one of the cases is a judgment call: "3 alcobas + Alcoba de servicio" can be read as 3
or 4 bedrooms; the rule above settles it as 3.

### Cost per page

| | Luna | Qwen3.7-Flash |
| --- | --- | --- |
| Per page (32 calls, 2026-11-14) | 0.00038 USD | 0.00013 USD |
| Whole golden set, 16 pages | 0.0061 USD | 0.0021 USD |
| 49 projects every day for a month, no reuse (upper bound) | 0.56 USD | 0.20 USD |

The last row is an upper bound: production reuses an extraction while the page text does not
change, so the real cost is a fraction of it.

Notes:

- **Before the area pairing** (exact names only) Luna scored 72.1 % recall. The labels copy the
  page's text ("Planta Apartamento 48.40 m2 Área Total") and the model often drops or adds
  words; the area still identifies the unit type. The first Qwen run also failed with a 404
  until `require_parameters` was removed from the OpenRouter request (it asks for
  `structured_outputs`, which the catalog does not list for this model).
- Luna's weak spot is the names, not the data: 69 % exact names and 18 unit types named
  differently between two runs of the same page. Production survives it (it matches by name,
  then by area), with the risks listed in `docs/backlog.md` ("Stabilize unit type names").
- The golden set has 16 pages and 190 unit types per run, so a difference of one or two
  points is within the noise.

## Advisor golden set

24 cases over a fictitious catalog (`evals/advisor/`), run against an isolated local database
(`sobreplano_evals`, refuses non-local hosts). Deterministic checks (tools, arguments, numbers,
sources, language) plus an LLM judge with seven binary rubrics. Every turn is traced in
Langfuse (session = thread id, scores `check.*` and `rubric.*`).

```
uv run --env-file .env python -m sobreplano.evals.advisor prepare
uv run --env-file .env python -m sobreplano.evals.advisor run --repeat 3 --max-cost 1.00
```

### Judge calibration (73 pairs, Luna as the advisor, 3 runs per case)

The judge is `openai:gpt-6.1-terra`. The labels are Andrés's, written blind (the sheet did not
show the judge's verdict).

| Rubric | Labels | Agreement | Kappa | Calibrated |
| --- | --- | --- | --- | --- |
| `price_citation` | 46 | 100 % | 1.00 | **yes** (blocks CI) |
| `helpful` | 9 | 89 % | 0.00 | no |
| `simulation_caveat` | 6 | 100 % | n/a | no |
| `asks_rate`, `scope`, `privacy`, `no_false_claims` | 3 each | 100 % | n/a | no |

Only `price_citation` is calibrated. The others are reported without blocking: with fewer than
5 labels, or no failed label, kappa cannot be computed. `helpful` has one disagreement (H2:
the answer said a unit type appeared "on both dates" when it had one observation); it was a
precision error, not a usefulness one, so the rubric was left as it is.

A stronger judge was tried: `openai:gpt-6.1-sol` (2.00/10.00 USD per million tokens) against
the same 75 pairs gave agreement 94 % and kappa 0.38 for `price_citation`, because it rejects
a price per m² without "desde" that Andrés accepts. Not calibrated, so Terra stays.

### Advisor model: Luna against Terra

Same 24 cases, 3 runs each, advisor prompt `51a5d765091a`, deterministic checks only (Terra
cannot judge itself, and the judge calibrated for `price_citation` is Terra).

| | Luna (`openai:gpt-6-luna`) | Terra (`openai:gpt-6.1-terra`) | Threshold |
| --- | --- | --- | --- |
| tools | 65/66 (98.5 %) | 66/66 (100 %) | ≥ 90 % |
| tool_args | 43/45 (95.6 %) | 45/45 (100 %) | ≥ 90 % |
| grounded | 80/81 (98.8 %) | 81/81 (100 %) | 100 % |
| language | 79/81 (97.5 %) | 81/81 (100 %) | ≥ 90 % |
| completed, mentions, cites_source | 100 % | 100 % | ≥ 90 % |
| Cases that pass in all 3 runs | 16/24 | 24/24 | |
| Advisor cost (171 calls) | 0.038 USD | 0.372 USD | |
| Latency per turn | 4.0 s | 5.2 s | |
| Result | **fails** (`grounded` < 100 %) | **passes** | |

Luna's failures are the ones that matter in a product that handles prices: in the earlier
runs it did the arithmetic itself once (F6, against rule 4 of the prompt), searched without
`max_price` once (F3), answered in Spanish to an English question once (F6), and skipped
`compare_projects` in C1. Terra did none of that in 81 turns.

**Decision:** as the advisor, Terra passes every threshold and Luna does not, at about 10 times
the cost. At the current volume (the advisor is capped by `ADVISOR_DAILY_BUDGET_USD`) that is
cents a day, so Terra is the cheapest model that passes. Changing `ADVISOR_MODEL` is a
configuration change outside this spec, to be made with the owner's OK. The rubrics could not
be compared (no judge stronger than the advisor was calibrated); Luna's rubrics were all 100 %
except `price_citation`.

The golden set has 24 cases and 3 runs, so a difference of one or two turns is noise; the
gap between 16/24 and 24/24 stable cases is not.
