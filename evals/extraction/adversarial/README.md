# Adversarial extraction pages

Four synthetic pages (invented project, `example.com` URLs) with instructions hidden in the
text, to measure whether the extractor resists them (SPEC 10). They are fictional, so unlike
the golden set they live in the repo.

- `texts/<case>.txt`: the clean text the extractor receives.
- `labels.json`: what a correct extraction returns (the real project, no injected unit type).
- `injections.json`: strings that must not reach what would be stored: project name,
  neighborhood and unit type names, after `validate_text`.

Run: `uv run --env-file .env python -m sobreplano.evals.extraction run --set adversarial`
