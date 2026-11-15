# Security (SPEC 10)

Work in progress: SPEC 10 step 11 and 12 turn this into the full threat model (one table per
asset, controls, where each is tested, what remains). What is here is what is already decided.

## Poisoned data from a scraped page

A developer's page reaches the advisor through the extractor, the database and the tools. Two
different attacks, two controls:

| Attack | Control | Where it is tested | What remains |
| --- | --- | --- | --- |
| **Injection**: text on the page tells the extractor to do something (change a price, name the project with a link, answer in a fixed way) | `extractor.md` treats `<page>` as data; `validate_text` refuses names and neighborhoods with line breaks, markup, URLs, emails or instruction words; the advisor treats tool results as data | `evals.extraction run --set adversarial`, measure `injection_followed` must be 0 | A text with no marker word that still reads as an instruction |
| **Forged block**: a well-formed unit type that is not real ("TIPO Z", price 100.000.000) | **The price per m² outlier rule** (`reject_price_outliers`): below 50 % or above 200 % of the median of the page's other unit types is refused. It is **not** the model: no extractor can tell a forged block from a real one | `tests/unit/domain/test_scraping.py`; `evals.extraction run --set adversarial`, measure `fake_block_stored` (expected 0); `tests/integration/test_golden_text_validation.py` (no real unit type of the 16 golden pages is refused) | A forged block with a believable price still enters. To do it, the attacker must compromise the developer's own site. With exactly 3 unit types, an extreme outlier also takes a real one with it |

Why the extractor prompt was not changed to fight forged blocks: the model's answer for the
forged block is correct for what it was given (a block with a name, price and areas). Asking it
to doubt well-formed blocks would cost real unit types and change the prompt version, which
re-extracts every page, for a control that the outlier rule already gives deterministically.
