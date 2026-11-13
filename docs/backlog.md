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
