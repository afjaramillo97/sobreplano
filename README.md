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

Tests: `uv run pytest -m "not integration"` needs no database; `uv run --env-file .env pytest` runs everything. Stop the database with `supabase stop`.

## Scraping policy

- One visit per site per day, with an identifying user-agent; robots.txt and each site's terms are respected.
- Only public project data (prices, areas, location). No personal data is collected or stored.

## Author

Built by Andrés Jaramillo as a portfolio project, end to end.

[andres-jaramillo.vercel.app](https://andres-jaramillo.vercel.app) · [LinkedIn](https://www.linkedin.com/in/AFJR)
