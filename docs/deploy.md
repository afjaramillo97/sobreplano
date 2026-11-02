# Deploy

How the daily scraper reaches production (SPEC 05): the one-time prerequisites, the cloud database, and how a run is deployed and checked. AWS accounts and access are in `docs/aws-accounts.md`.

This repo is public: account IDs, project refs, passwords and keys are **not** written here. Where a name contains the account ID it appears as `<account-id>`.

## How it runs

```text
EventBridge Scheduler (06:00 America/Bogota, var.scrape_schedule)
  -> Lambda sobreplano-scraper (container image, arm64, 512 MB, 10 min)
       reads DATABASE_URL and OPENAI_API_KEY from SSM at cold start
       fetches the developer's site, writes raw HTML to S3
       extracts with the LLM, writes to Supabase (transaction pooler, port 6543)
  -> on error: CloudWatch alarm -> SNS -> email; Lambda retries twice

push to main (src/, Dockerfile, uv.lock) -> GitHub Actions (OIDC) -> ECR -> update the Lambda
```

| Piece | Where |
| --- | --- |
| Infrastructure | `infra/` (Terraform, applied by hand) |
| Image | `Dockerfile` |
| Lambda entry point | `src/sobreplano/interface/lambda_handler.py` |
| Image deploy | `.github/workflows/deploy-scraper.yml` |

## Prerequisites (done once, by hand)

All AWS resources live in the `sobreplano-prod` account, region `us-east-1`. Sign in first with `eval "$(scripts/aws-sso.sh)"`.

| What | Name | Notes |
| --- | --- | --- |
| Supabase project | `sobreplano` | Region `us-east-1`, Free plan. Connection string in the git-ignored `.env.cloud` |
| Terraform state bucket | `sobreplano-tfstate-<account-id>-us-east-1-an` | Versioned, all public access blocked; locking with `use_lockfile` |
| SSM parameter | `/sobreplano/prod/database_url` | `SecureString`. Supabase shared pooler, transaction mode (port 6543) |
| SSM parameter | `/sobreplano/prod/openai_api_key` | `SecureString` |

| GitHub secret | `AWS_DEPLOY_ROLE_ARN` | The `github_deploy_role_arn` Terraform output. The only secret in the repository; there are no AWS keys in GitHub |
| `.env` (local) | `TF_STATE_BUCKET`, `TF_VAR_alert_email` | Terraform's backend bucket and the alert email, kept out of the public repo |

Upload or rotate the SSM parameters with `scripts/sync-ssm-secrets.sh` (`--dry-run` to preview). Terraform only knows the parameter names, so the values never enter its state. The Lambda reads them once per container, so a rotated value takes effect at the next cold start. To force one, run `deploy-scraper.yml` by hand (`workflow_dispatch`): a new deploy starts fresh containers. Do not edit the function's settings in the console or the CLI; Terraform would show the change as drift.

Set the GitHub secret once, after the first `terraform apply`:

```bash
gh secret set AWS_DEPLOY_ROLE_ARN --body "$(terraform -chdir=infra output -raw github_deploy_role_arn)"
```

## Database connections

| Use | Connection | Port |
| --- | --- | --- |
| Lambda | Shared pooler, transaction mode | 6543 |
| Alembic, `pg_dump` and `psql` from a laptop | Shared pooler, session mode | 5432 |
| Local development | Local Supabase | 54322 |

The direct connection is IPv6-only on the Free plan, so everything goes through the shared pooler. Transaction mode does not support prepared statements; the engine turns them off for port 6543.

## Migrating the cloud database

`.env.cloud` holds the session-pooler URL, so Alembic runs against the cloud exactly as it does locally. **Migrate before merging code that needs the new schema**: the merge deploys the image at once, and the next run would fail against the old schema.

```bash
uv run --env-file .env.cloud alembic upgrade head
uv run --env-file .env.cloud alembic check
```

## Copying the local history to the cloud

Done once, on 2026-11-01, before the first cloud run, with the cloud database freshly migrated and empty. It preserves the price history recorded locally on 2026-10-30 and 2026-10-31. The `price_observations` triggers only block `UPDATE`, `DELETE` and `TRUNCATE`, so the `INSERT`s load fine.

`pg_dump` and `psql` come from `libpq` (`brew install libpq`, keg-only). SQLAlchemy URLs use `postgresql+psycopg://`; the libpq tools need plain `postgresql://`. Keep the dump outside the repo: scraped data is never committed.

```bash
export PATH="/opt/homebrew/opt/libpq/bin:$PATH"
set -a; source .env; set +a;       LOCAL="${DATABASE_URL/postgresql+psycopg/postgresql}"
set -a; source .env.cloud; set +a; CLOUD="${DATABASE_URL/postgresql+psycopg/postgresql}"

pg_dump "$LOCAL" --data-only --no-owner --no-privileges \
  -t developers -t projects -t unit_types -t price_observations \
  -t scrape_runs -t scraped_pages -t page_extractions \
  -f /tmp/history.sql

psql "$CLOUD" -v ON_ERROR_STOP=1 --single-transaction -f /tmp/history.sql
rm /tmp/history.sql

for t in developers projects unit_types price_observations scrape_runs scraped_pages page_extractions; do
  printf "%-20s %6s %6s\n" "$t" \
    "$(psql "$LOCAL" -Atc "select count(*) from $t")" \
    "$(psql "$CLOUD" -Atc "select count(*) from $t")"
done
```

Result on 2026-11-01 (local and cloud):

| Table | Local | Cloud |
| --- | ---: | ---: |
| `developers` | 2 | 2 |
| `projects` | 24 | 24 |
| `unit_types` | 52 | 52 |
| `price_observations` | 96 | 96 |
| `scrape_runs` | 2 | 2 |
| `scraped_pages` | 42 | 42 |
| `page_extractions` | 42 | 42 |

## Applying Terraform

`infra/` is applied from a laptop by an admin, never from CI. Sign in, then load the two Terraform variables from `.env` (see `.env.example`):

```bash
eval "$(scripts/aws-sso.sh)"
eval "$(grep -E '^(TF_STATE_BUCKET|TF_VAR_alert_email)=' .env | sed 's/^/export /')"

terraform -chdir=infra init -backend-config="bucket=$TF_STATE_BUCKET"
terraform -chdir=infra plan -out=tfplan
terraform -chdir=infra apply tfplan
```

### First apply only: the bootstrap image

The Lambda cannot be created before its image exists in ECR. The first time, create the repository alone, push the local image as `bootstrap`, then apply the rest. Afterwards GitHub Actions deploys every commit to `main`, and Terraform ignores `image_uri`.

```bash
terraform -chdir=infra apply -target=aws_ecr_repository.scraper
REPO="$(terraform -chdir=infra output -raw ecr_repository_url)"
aws ecr get-login-password | docker login --username AWS --password-stdin "${REPO%%/*}"
docker build --platform linux/arm64 --provenance=false -t "$REPO:bootstrap" .
docker push "$REPO:bootstrap"
terraform -chdir=infra apply
```

### New-account limits

A new AWS account starts with low Lambda limits. On 2026-11-01 `sobreplano-prod` had 5 concurrent executions and a 512 MB memory cap (`CreateFunction` rejected 1024 MB). Hence 512 MB and no reserved concurrency; one run per developer per day is enforced in the database instead (SPEC 05). An increase to 1000 concurrent executions was requested in Service Quotas.

After the first apply, confirm the SNS subscription from the email AWS sends, or the error alarm reaches nobody.

## Deploying code

Merging to `main` a change under `src/`, the `Dockerfile` or `uv.lock` runs `deploy-scraper.yml`: it builds the image on a native arm64 runner, pushes it to ECR tagged with the commit SHA and the run ID, and points the Lambda at that image by digest. Run it again by hand from the Actions tab (`workflow_dispatch`). Check what is deployed:

```bash
aws lambda get-function --function-name sobreplano-scraper \
  --query '{image:Code.ResolvedImageUri,state:Configuration.State,updated:Configuration.LastModified}'
```

Infrastructure changes (`infra/`) are never applied from CI: CI only runs `terraform fmt -check` and `terraform validate`. Apply them by hand as above, after reading the plan.

## Changing the schedule

The schedule is the `scrape_schedule` Terraform variable, in Bogotá time (default `cron(0 6 * * ? *)`, every day at 06:00). For example, Mondays and Thursdays:

```bash
terraform -chdir=infra plan -var 'scrape_schedule=cron(0 6 ? * MON,THU *)' -out=tfplan
terraform -chdir=infra apply tfplan
```

Keep the value in `.env` as `TF_VAR_scrape_schedule` so later applies do not revert it.

## Running the scraper by hand

```bash
aws lambda invoke --function-name sobreplano-scraper \
  --payload '{"developer":"londono-gomez"}' \
  --cli-binary-format raw-in-base64-out --log-type Tail out.json
cat out.json
```

`--log-type Tail` returns the last 4 KB of the log. `out.json` holds the `ScrapeReport`: `succeeded` or `skipped`. A `failed` run raises instead, so Lambda counts an error, the alarm emails and Lambda retries twice. A second run on the same day ends `skipped` without visiting the site.

## When the alarm emails

The alarm fires when the Lambda raises: a `failed` run (no page got a price, or the listing could not be fetched), a timeout, or a crash. Lambda retries twice within minutes; the retries are safe, and once one succeeds the rest end `skipped`.

1. Read the run's summary in the logs (below) and `scrape_runs.error`.
2. If the site blocked the request or changed its markup, fix the scraper and merge; run it by hand once deployed.
3. If the database did not answer, check that the Supabase project is not paused (the Free plan pauses after 7 days without activity).

## Checking a run

- Logs: `aws logs tail /aws/lambda/sobreplano-scraper --since 1d`. Each run ends with the same summary the CLI prints, then a `REPORT` line with the duration and `Max Memory Used`.
- Raw HTML: `aws s3 ls "s3://$(terraform -chdir=infra output -raw raw_html_bucket)/londono-gomez/" --recursive`.
- Database: `select run_on, status, pages_fetched, observations_recorded, error from scrape_runs order by started_at desc limit 5;` with `psql` and `.env.cloud`.

## First run in AWS (2026-11-01)

Manual invocation from a laptop, before the first scheduled run:

```text
status: succeeded
pages: 25 listed, 21 fetched, 3 out of scope, 1 failed
projects added: 0, unit types added: 0
unit types: 45 valid, 33 rejected
observations: 44 recorded, 1 already recorded today
extractions: 21 new, 0 reused
tokens (openai:gpt-6-luna): 31687 input, 3859 output
estimated cost: 0.0051 USD
failed: https://londonogomez.com/node/203631: no Google Maps directions link in .../ezzenti
REPORT Duration: 86349.08 ms  Memory Size: 512 MB  Max Memory Used: 238 MB
```

Second invocation the same day: 175 ms, no HTTP requests:

```text
status: skipped
reason: a run already succeeded on 2026-11-01
```

`scrape_runs` in the cloud database afterwards:

| run_on | status | pages_fetched | observations_recorded |
| --- | --- | ---: | ---: |
| 2026-10-30 | succeeded | 21 | 44 |
| 2026-10-31 | succeeded | 21 | 44 |
| 2026-11-01 | succeeded | 21 | 44 |
| 2026-11-01 | skipped | 0 | 0 |

The first two rows are the local history copied above.

Raw HTML in S3 afterwards: `aws s3 ls "s3://<bucket>/londono-gomez/" --recursive | wc -l` gives `21`, all under `londono-gomez/2026-11-01/`, about 132 KB each (2.7 MB in total), with `ContentType: text/html; charset=utf-8` and SSE-S3 (`AES256`).

No extraction was reused: the HTML of all 21 pages differed from 2026-10-31, so every raw-HTML hash was new. At 0.005 USD a run this is negligible for one developer; if the HTML keeps changing every day, a later spec should hash the cleaned page text instead.
