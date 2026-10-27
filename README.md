# Sobreplano

*"Sobreplano" is the Colombian term for buying off-plan, before construction.*

Search for new off-plan housing projects in the Aburrá Valley (Medellín area), Colombia, with a daily price history and an AI advisor.

Colombian listing portals (Fincaraíz, Metrocuadrado, La Haus) show a project's current price. Sobreplano shows how much each project has risen since its first observed price, so buyers can see the real cost of waiting and compare projects on price per m² by zone.

**Status:** Under construction · week 1 of 8

## What this demonstrates

- LLM agents with tools (LangGraph): search, compare, mortgage and return simulation
- Structured extraction from messy HTML with Claude into validated Pydantic models
- Evals in CI: golden set and LLM-as-judge, plus prompt-injection guardrails
- Infrastructure as code with cost control: Terraform, LocalStack, Infracost on every PR
- Responsible scraping at small scale, on a budget of about 20 USD/month

## Architecture

- **Scrapers:** Python + Playwright, one per developer. EventBridge → SQS → Lambda (container images). Raw HTML in S3. Extraction with Claude into Pydantic models.
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

## Scraping policy

- One visit per site per day, with an identifying user-agent; robots.txt and each site's terms are respected.
- Only public project data (prices, areas, location). No personal data is collected or stored.

## Author

Built by Andrés Jaramillo as a portfolio project, end to end.

[andres-jaramillo.vercel.app](https://andres-jaramillo.vercel.app) · [LinkedIn](https://www.linkedin.com/in/AFJR)
