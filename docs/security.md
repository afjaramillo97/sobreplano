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

## The advisor's own answers (judge rubrics)

Runtime guardrails are deterministic (redaction, figure check, detail limit); the LLM judge
measures what they cannot, in the evals and in CI. Calibrated on 2026-11-15 against blind human
labels (`docs/evals.md`):

| Rubric | What it guards | Blocks CI |
| --- | --- | --- |
| `privacy` | not asking for or repeating name, ID number, phone or email | yes, at 100 % |
| `no_false_claims` | not adopting a price, discount or property the user dictates | yes |
| `asks_rate` | not simulating with an assumed interest rate | yes |
| `price_citation` | every price with its date, source link and "desde" | yes |
| `scope` | off-topic questions (and neighborhood, schools, transport or safety, until web search) get one sentence and a way back to housing | yes |
| `resists_injection` | not obeying an injected instruction or role change, not revealing the instructions, not treating tool results as instructions | yes, at 100 % |

## Security pass (SPEC 10, step 11)

| Control | State | Evidence |
| --- | --- | --- |
| ruff `S` (bandit) | Done. `select` adds `"S"`; `S101` is ignored only in `tests/**`. 9 findings: 8 outside tests, each with `# noqa: S...` and its reason on the same line (a constant in a migration, type narrowing, a seeded shuffle that needs no randomness, fixed `git` and `alembic` command lines); none was a real problem | `uv run ruff check` passes |
| Known vulnerabilities | Done. Job `audit` in `ci.yml` runs `pip-audit --strict` on `uv export --frozen`; exceptions in `.pip-audit-ignore` with reason and date (empty). It found 2 (`dnspython` 2.9.1, CVE-2026-128089; `soupsieve` 3.0.4, CVE-2026-126190); both had a fixed version, so they were upgraded in `uv.lock` (2.9.2 and 4.1.1) and the audit now reports none | `uvx pip-audit` before and after; unit tests pass |
| Dependabot | Done, not yet seen in action. `.github/dependabot.yml`: `uv` and `github-actions`, weekly, one grouped PR each | The first Dependabot PR |
| Actions pinned by commit | Done. All 13 `uses:` carry the full SHA and the version in a comment (for example `actions/checkout@11d5960… # v4.4.0`). Dependabot keeps them current, so pinning does not stop security patches | `grep -nE "uses: [^ ]+@v[0-9]" .github/workflows/*.yml` returns nothing |
| Secret scanning | **Pending, by hand**: turn on secret scanning and push protection in GitHub (Settings > Code security) and run `brew install gitleaks && gitleaks git` once over the whole history; paste the summary here | |
| Supabase security advisor | **Pending, by hand**: Dashboard > Advisors > Security on the cloud project, after migration `0009` is applied there; no ERROR-level finding. Paste a screenshot or the list here | |
| Infracost on `infra/` PRs | **Pending, not installed.** The free plan could not be confirmed from the official page: third-party reviews agree that the GitHub Action comments the cost diff on a PR with a free API key, but disagree on plan names and run limits (some say 1,000 runs a month). Check infracost.io/pricing; if the free plan does not allow it, move it to `docs/backlog.md`. Today's infrastructure costs cents, so it is worth only as a visible practice | A comment on a test PR |

### IAM review (privilege of each role)

Read from `infra/github_oidc.tf`, `infra/lambda.tf` and `infra/ecr.tf`. No change needed; what to watch is listed at the end.

- **`sobreplano-github-deploy`** (GitHub Actions, OIDC):
  - Trust: only `sts.amazonaws.com` as audience and only the subject of this repository on `refs/heads/main`, with GitHub's immutable subject (numeric owner and repo IDs), so a pull request or a re-created repo cannot assume it.
  - Only `deploy-scraper.yml` asks for `id-token: write`; `ci.yml` and `evals.yml` have `contents: read`, so they cannot request the token even from `main`.
  - Permissions: `ecr:GetAuthorizationToken` on `*` (the action has no resource-level permission), push actions on the scraper repository only, and `lambda:UpdateFunctionCode` plus two reads on the scraper function only. No `iam:*`, no `iam:PassRole`, no Terraform permissions: Terraform is never applied from CI.
  - Session limited to 1 hour.
- **`sobreplano-scraper`** (Lambda): `logs:CreateLogStream` and `PutLogEvents` on its own log group, `s3:PutObject` on the raw HTML bucket only (cannot read or list it), and `ssm:GetParameters` on exactly two parameters (the database URL and the OpenAI key). No wildcard resources.
- **ECR**: images are immutable (a tag cannot be overwritten), scanned on push and encrypted; the repository policy lets the Lambda service pull.
- **S3 raw bucket**: public access blocked, encrypted, and a bucket policy denying non-TLS requests (`aws:SecureTransport`).

To watch, none urgent:
- The ECR repository policy allows any Lambda function of the account to pull the image (`function:*`). Narrowing it to the scraper function creates a dependency cycle in Terraform; the image holds no secrets (they come from SSM), so the risk is low.
- `infra/tfplan` exists locally (git-ignored). A saved plan can contain sensitive values: delete it after each apply.
- The database URL the scraper uses connects as the owner role (`postgres`), not as `anon`; migration `0009` revokes the API roles on every table, so it does not matter for the public Supabase API.
