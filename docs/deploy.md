# Deploy

How the daily scraper reaches production (SPEC 05): the one-time prerequisites, the cloud database, and how a run is deployed and checked. AWS accounts and access are in `docs/aws-accounts.md`.

This repo is public: account IDs, project refs, passwords and keys are **not** written here. Where a name contains the account ID it appears as `<account-id>`.

## Prerequisites (done once, by hand)

All AWS resources live in the `sobreplano-prod` account, region `us-east-1`. Sign in first with `eval "$(scripts/aws-sso.sh)"`.

| What | Name | Notes |
| --- | --- | --- |
| Supabase project | `sobreplano` | Region `us-east-1`, Free plan. Connection string in the git-ignored `.env.cloud` |
| Terraform state bucket | `sobreplano-tfstate-<account-id>-us-east-1-an` | Versioned, all public access blocked; locking with `use_lockfile` |
| SSM parameter | `/sobreplano/prod/database_url` | `SecureString`. Supabase shared pooler, transaction mode (port 6543) |
| SSM parameter | `/sobreplano/prod/openai_api_key` | `SecureString` |

Upload or rotate the SSM parameters with `scripts/sync-ssm-secrets.sh` (`--dry-run` to preview). Terraform only knows the parameter names, so the values never enter its state.

## Database connections

| Use | Connection | Port |
| --- | --- | --- |
| Lambda | Shared pooler, transaction mode | 6543 |
| Alembic, `pg_dump` and `psql` from a laptop | Shared pooler, session mode | 5432 |
| Local development | Local Supabase | 54322 |

The direct connection is IPv6-only on the Free plan, so everything goes through the shared pooler. Transaction mode does not support prepared statements; the engine turns them off for port 6543.

## Migrating the cloud database

`.env.cloud` holds the session-pooler URL, so Alembic runs against the cloud exactly as it does locally:

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
