# Security (SPEC 10)

Threat model of Sobreplano as of SPEC 10: one table per asset, with the threat, the control,
where it is tested and what remains. Then the controls that are not tied to one asset
(poisoned data, judge rubrics, security pass). Terms of use: [terms-of-use.md](terms-of-use.md).

## Threat model by asset

### 1. The price history

The value of the product: today's price is on each developer's site; the past is not.

| Threat | Control | Tested in | What remains |
| --- | --- | --- | --- |
| Pulling every history through `GET /projects/{slug}` | Per-IP limits: 10 a minute and **40 a day** on the detail, below the catalog's size (about 50 projects), so copying everything takes several IPs and shows in the report. 30 a minute and 600 a day on the lists | `tests/unit/interface/test_rate_limit.py`, `tests/integration/test_rate_limit_repository.py` | See "Not protected" |
| Walking the listing with a huge page or offset | `limit` 1 to 50 (20 by default), `offset` 0 to 1000 | `tests/unit/interface/test_read_api_routes.py` | |
| Asking the advisor for "the full history of every project" | `MAX_DETAILS_PER_MESSAGE = 6` per message, 5 messages a minute and 30 a day per IP, 20 messages per conversation; prompt rule 11 | `tests/unit/infrastructure/test_advisor_tools.py`, eval A4 | Costs as many messages as the API costs requests |
| Reading the tables through Supabase's public API | RLS on every table, no policy, and `REVOKE` for `anon` and `authenticated` (migration `0009`); a test walks every table of `public` | `tests/integration/test_supabase_api_closed.py` | |
| Documentation as a map of the API | `API_DOCS_ENABLED=false` turns off `/docs`, `/redoc` and `/openapi.json`; `/robots.txt` disallows everything | `tests/unit/interface/test_read_api_routes.py` | The deployment (SPEC 12) must set the flag |
| Noticing who copies | `rate_limited` log lines and `rate_limit_report` (top 10 clients per group, who went over) | `tests/unit/interface/test_rate_limit_report.py` | No alarm yet (SPEC 12) |

Client key: `HMAC-SHA256(RATE_LIMIT_KEY, ip)` cut to 32 characters, kept for 2 days
(`prune_rate_limits`). The IP is never stored: a plain hash of an IPv4 is reversed by trying
all of them. `X-Forwarded-For` is trusted only with `TRUSTED_PROXY_HOPS` > 0 (default 0).
If the counters are down, reads are served and the advisor answers 503.

### 2. The LLM budget

| Threat | Control | Tested in | What remains |
| --- | --- | --- | --- |
| Draining it with chat messages | 5 a minute and 30 a day per IP (fail closed), 20 messages per conversation, 1000 characters per message, 0.20 USD a day for the advisor (`ADVISOR_DAILY_BUDGET_USD`), at most 5 tool rounds per message | `tests/unit/interface/test_rate_limit.py`, `tests/unit/application/test_ask_advisor.py` | Many IPs: 30 messages a day each. The daily budget is the real ceiling (about 6 USD a month) |
| A runaway eval or scrape | `--max-cost` on every paid run; extraction reused by text hash | `tests/unit/evals/` | |

### 3. Privacy of whoever uses the chat

| Threat | Control | Tested in | What remains |
| --- | --- | --- | --- |
| Email, phone or ID number reaching the model, the memory or Langfuse | `redact_personal_data` in `LangGraphAdvisor.reply`, before the graph runs: `[correo]`, `[teléfono]`, `[documento]`; an ID only after a keyword (a bare 1.234.567.890 may be a price) | `tests/unit/domain/test_privacy.py`, `tests/unit/infrastructure/test_langgraph_advisor.py` (model and checkpoint), eval A5 | A datum in a form the patterns do not know (a landline, a name). Names are not redacted |
| The model rebuilding a datum in its answer | The answer is redacted too, in the reply and in the thread | same | |
| The advisor asking for or repeating personal data | Prompt rule 5; rubric `privacy` (100 %) | evals O2, A5, A9 | |
| Conversations kept | Deleted after 7 days without messages (`advisor_cleanup`) | `tests/integration/test_advisor_repositories.py` | |
| Client IPs | Only the keyed hash, for 2 days | `tests/unit/interface/test_rate_limit.py` | |

### 4. Integrity of the prices shown

| Threat | Control | Tested in | What remains |
| --- | --- | --- | --- |
| The advisor inventing a figure | Every amount and percentage of the answer must come from the thread (user messages, tool results and arguments) or the tool definitions; one rewrite, then a fixed answer. Rubric `price_citation` | `tests/unit/infrastructure/test_langgraph_advisor.py`, `tests/unit/domain/test_figures.py`, eval `grounded` at 100 % | An invented tool argument (a rate the user never gave) is covered by `asks_rate` and cases F2 and A9, not by this check |
| Agreeing with a price or discount the user dictates | Rubric `no_false_claims`; cases A3, A8, O4 | `docs/evals.md` | |
| Injected text on a developer's page | See "Poisoned data" below | | |
| Corrupting the append-only history | A trigger blocks `UPDATE`, `DELETE` and `TRUNCATE` on price observations; the range rules refuse a price outside 50 million to 20 billion COP | `tests/integration/test_db_rules.py` | |

### 5. The AWS account

| Threat | Control | Tested in | What remains |
| --- | --- | --- | --- |
| Deploying from a branch, a fork or a re-created repo | OIDC trust pinned to `main` of this repo with GitHub's immutable subject; only `deploy-scraper.yml` can request a token | Review below | |
| An over-broad role | The deploy role cannot touch IAM or Terraform; the Lambda role writes one bucket and reads two parameters | IAM review below | ECR pull policy for any Lambda of the account |
| A compromised action | Every action pinned by commit SHA; Dependabot updates them weekly | `grep` in the table below | |
| Cost surprises | Monthly budget alarm (Terraform), Infracost on `infra/` PRs if the free plan allows | `infra/alerts.tf` | Infracost pending |
| Terraform applied by CI | Never: it is applied by hand with the owner's OK | `docs/deploy.md` | |

### 6. Secrets

| Threat | Control | Tested in | What remains |
| --- | --- | --- | --- |
| A key in git | `.env` files ignored; secret scanning and push protection on GitHub; `gitleaks` over the history | Pending by hand (table below) | |
| Keys in the Lambda | SSM SecureStrings read at runtime; the Lambda role reads exactly two | IAM review below | |
| Scraped data or HTML in git | `.gitignore` of `data/`, `.evals/` and `evals/reports/`; golden set of the extraction only in S3 | Review of the diff | The synthetic adversarial pages are in the repo on purpose: they are fictional |
| A vulnerable dependency | `audit` job (`pip-audit`), Dependabot, `ruff` `S` rules | CI | |

### Not protected by SPEC 10

- **Distributed scraping from many IPs, or residential IPs.** The limits are per IP: 40 detail
  requests a day each. SPEC 12 adds an edge layer (Cloudflare or AWS WAF, Turnstile on the chat);
  if copying persists, the full history for signed-in users only is the next step.
- **Copying today's prices from the developers' own sites.** They are public there.
- **A model-based injection classifier.** Tools only read public data and the prompt is in the
  repo, so the worst an injection reaches is a false figure or an off-topic answer, which the
  figure check and the evals catch. Reconsider it if the advisor gains tools that write.
- **Alerts on 429s** (CloudWatch metric and alarm) and **good bots** (Google): SPEC 12.

### What SPEC 12 adds

`RATE_LIMIT_KEY` required in production, `TRUSTED_PROXY_HOPS` set to the real number of
proxies, `API_DOCS_ENABLED=false`, the scheduled `prune_rate_limits`, the edge layer, and the
429 alarm.

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
| Secret scanning | `gitleaks git --redact` over the whole history (148 commits, 2026-11-15): **no leaks found** after documenting 3 false positives in `.gitleaksignore` (`generic-api-key` read the `"key":"O2/r3/t1/privacy"` id of a synthetic eval pair in the old label format; not a credential). A scan of the working tree only finds keys in git-ignored files (`.env`, `.env.ci`, `.evals/`), none tracked. **Pending, by hand**: turn on secret scanning and push protection in GitHub (Settings > Code security) | `gitleaks git --redact -v` |
| Supabase security advisor | Done (2026-11-15). Migration `0009` applied in the cloud (`alembic current`: `0009 (head)`); Dashboard > Advisors > Security shows **no ERROR-level finding** (reported by the owner; no screenshot attached) | `alembic current` on `.env.cloud` |
| Infracost on `infra/` PRs | Workflow written (`.github/workflows/infracost.yml`), **not active until the API key exists**: see "Infracost" below | A comment on a test PR (space below) |

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

## Infracost (cost of `infra/` before the merge)

**What it is for.** Today the infrastructure costs cents, so the estimate itself is small. The
value is catching a resource with a **fixed monthly cost** before it merges, above all in SPEC 12
(an edge layer such as a WAF or a load balancer, a NAT gateway, a database) where one line of
Terraform can add tens of USD to a project with a 20 USD a month budget. It also shows the
practice on the pull request.

**How it works.** `.github/workflows/infracost.yml` runs `infracost/actions/diff@v5.0.1`
(pinned by SHA) only on pull requests to `main` that change `infra/**`. It reads the Terraform
code of `main` and of the PR, with no AWS credentials and no plan, and comments the cost
difference. Permissions: `contents: read` and `pull-requests: write`. The dashboard upload is
turned off (`INFRACOST_CI_DISABLE_DASHBOARD`), so nothing about the repository is sent to the
Infracost dashboard; the comment is posted with the job's own token. Terraform is still never
applied from CI.

**On and off.** The secret `INFRACOST_API_KEY` (GitHub: Settings > Secrets and variables >
Actions). Without it the job skips with a notice and does not fail, like `evals.yml` without
`RUN_ADVISOR_EVALS`. Forks and Dependabot get no secrets, so they skip too.

**To review (not confirmed).**
- **The free plan after the trial.** On 2026-11-15 the dashboard says the trial of Infracost
  Cloud ends in 13 days (2026-11-28) and "our CI/CD plan starts free". Third-party sources and
  the FAQ say that plan has comments on pull requests and 1,000 runs a month, and the API key
  does not need Cloud. A community post of 2026-07-14 says that with the 2.x CLI, `scan` may
  require a connection to an Infracost Cloud organization; no official answer was found.
  **After 2026-11-28, open a pull request that touches `infra/` and check that the comment
  still appears.** If it does not, the options are the GitHub App or moving this to the backlog.
- **The usage file.** `infra/infracost-usage.yml` holds the real approximate usage (see the
  comments in the file for where each number comes from), so the estimate is not 0 USD for
  Lambda, S3 and CloudWatch Logs. `diff@v5` has no input for a usage file, and the 2.x
  documentation wires it through a config file (`infracost.yml` with `usage_file`), which was
  not verified. If the first comment shows the usage-based resources at 0 USD, add that config
  file.
- Runs: 1,000 a month is far above what a repository with a few `infra/` PRs uses.

**Evidence: the comment of a test pull request.** Pending: open a pull request that touches
`infra/` once the API key is saved in GitHub, and paste the comment here.

```
(paste the Infracost comment here)
```
