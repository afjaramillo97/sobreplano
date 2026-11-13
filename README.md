# Sobreplano

*"Sobreplano" is the Colombian term for buying off-plan, before construction.*

Search for new off-plan housing projects in the Aburrá Valley (Medellín area), Colombia, with a daily price history and an AI advisor.

Colombian listing portals (Fincaraíz, Metrocuadrado, La Haus) show a project's current price. Sobreplano shows how much each project has risen since its first observed price, so buyers can see the real cost of waiting and compare projects on price per m² by zone.

**Status:** Under construction · week 3 of 8

## What this demonstrates

- LLM agents with tools (LangGraph): search, compare, mortgage and return simulation
- Structured extraction from messy HTML with an LLM (provider-agnostic; GPT-6 Luna today) into validated Pydantic models
- Evals in CI: golden set and LLM-as-judge, plus prompt-injection guardrails
- Infrastructure as code with cost control: Terraform, LocalStack, Infracost on every PR
- Responsible scraping at small scale, on a budget of about 20 USD/month

## Architecture

Running today: a daily scraper in AWS writing the price history to Supabase.

```text
EventBridge Scheduler, 06:00 Bogotá
  -> Lambda (container image, arm64)
       -> developer's website (httpx, robots.txt, one visit a day)
       -> raw HTML to S3
       -> LLM extraction into Pydantic models
       -> Supabase Postgres (one price per unit type per day, append-only)
  -> errors: CloudWatch alarm -> email
```

All of it is Terraform (`infra/`). GitHub Actions deploys the image through OIDC, with no AWS keys stored in GitHub. The database allows one run per developer per day, so a retry or a manual run never visits a site twice. It costs well under 1 USD a month.

The full picture, as planned:

- **Scrapers:** Python + httpx, one per developer (Playwright only when a site needs a browser). EventBridge → SQS → Lambda (container images). Raw HTML in S3. LLM extraction into Pydantic models.
- **Data:** Supabase (Postgres with pgvector and PostGIS, Supabase Auth). Migrations with Alembic.
- **API:** FastAPI + SQLAlchemy.
- **Advisor:** LangGraph with tools to search, compare, and simulate mortgage and investment return. Hybrid search, RAG over housing subsidies, and a custom MCP server.
- **Quality:** golden set and LLM-as-judge in CI, guardrails against prompt injection in scraped content, Langfuse.
- **Frontend:** React + Vite with a tRPC BFF.
- **Infra:** Terraform, LocalStack for local testing, Infracost on PRs, GitHub Actions.

## Roadmap

| Week | Focus |
| --- | --- |
| 1 | Planning |
| 2 | Monorepo foundations and schema |
| 3 | Scrapers and first daily snapshot |
| 4 | History, price per m² by zone, and API |
| 5 | AI advisor |
| 6 | Evals and guardrails |
| 7 | Frontend |
| 8 | Launch and demo |

## Run locally

Needs [uv](https://docs.astral.sh/uv/), Docker and the [Supabase CLI](https://supabase.com/docs/guides/local-development/cli/getting-started) (`brew install supabase/tap/supabase`).

```bash
uv sync
cp .env.example .env                                              # local DATABASE_URL
supabase db start                                                 # Postgres on port 54322
uv run --env-file .env alembic upgrade head                       # create the schema
uv run --env-file .env python -m sobreplano.interface.cli.seed    # load seeds/projects.json
uv run --env-file .env uvicorn sobreplano.interface.api.main:app  # API on http://localhost:8000
```

Then open [localhost:8000/docs](http://localhost:8000/docs), or:

```bash
curl -s localhost:8000/health
curl -s "localhost:8000/projects?municipality=envigado" | jq '.items[0].unit_types'
```

The read API (SPEC 07) answers what exists with given conditions, what it costs today and how much it has risen since its first observed price:

```bash
# Search: one unit type must meet every price, bedroom and area filter at once.
# sort is "name" (default) or "price"; a project lists only the unit types that match.
curl -s "localhost:8000/projects?developer=constructora-capital&max_price=500000000&min_bedrooms=2&sort=price&limit=20" \
  | jq '.items[] | {name, unit_types: [.unit_types[] | {name, latest_price, change_since_first_pct}]}'

# One project with the whole price history of each unit type (404 if the slug does not exist)
curl -s localhost:8000/projects/axis-ciudad-peldar \
  | jq '.unit_types[] | {name, first_price, change_since_first_pct, history}'

# Developers with their number of projects; the slug is what ?developer= takes
curl -s localhost:8000/developers
```

The advisor (SPEC 08) answers in natural language with that same data and remembers the conversation by `thread_id`; it needs `OPENAI_API_KEY` in `.env`:

```bash
curl -s -X POST localhost:8000/advisor/chat -H 'content-type: application/json' \
  -d '{"message": "Busco 3 alcobas en Sabaneta por menos de 450 millones"}'
uv run --env-file .env python -m sobreplano.interface.cli.advise   # chat in the terminal
```

Tools, limits, retention and cost: [docs/advisor.md](docs/advisor.md).

Tests: `uv run pytest -m "not integration"` needs no database; `uv run --env-file .env pytest` runs everything. Stop the database with `supabase stop`.

Production (AWS, Terraform, deploys and how to check a run): [docs/deploy.md](docs/deploy.md).

## Scraping policy

- One visit per site per day, with an identifying user-agent; robots.txt and each site's terms are respected.
- Only public project data (prices, areas, location). No personal data is collected or stored.

## Author

Built by Andrés Jaramillo as a portfolio project, end to end.

[andres-jaramillo.vercel.app](https://andres-jaramillo.vercel.app) · [LinkedIn](https://www.linkedin.com/in/AFJR)
