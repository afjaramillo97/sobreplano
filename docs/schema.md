# Database schema

Postgres (Supabase, local via `supabase db start`) with PostGIS. Alembic is the only owner of the schema: see `migrations/versions/` (`0001` schema v1, `0002` scraping). The models live in `src/sobreplano/infrastructure/db/models.py`.

```mermaid
erDiagram
    developers ||--o{ projects : builds
    projects ||--o{ unit_types : offers
    unit_types ||--o{ price_observations : "is priced by"
    developers ||--o{ scrape_runs : "is scraped by"
    scrape_runs ||--o{ scraped_pages : fetches

    developers {
        uuid id PK
        text name
        text slug UK
        text website_url
        timestamptz created_at
        timestamptz updated_at
    }
    projects {
        uuid id PK
        uuid developer_id FK
        text name
        text slug UK
        varchar municipality "CHECK: 10 municipalities"
        text neighborhood "nullable"
        geography location "POINT, 4326, GIST index"
        text source_url
        timestamptz created_at
        timestamptz updated_at
    }
    unit_types {
        uuid id PK
        uuid project_id FK
        text name "unique per project"
        numeric private_area_m2 "nullable, 7.2"
        numeric built_area_m2 "nullable, 7.2"
        smallint bedrooms "nullable since 0002"
        smallint bathrooms "nullable since 0002"
        timestamptz created_at
        timestamptz updated_at
    }
    price_observations {
        uuid id PK
        uuid unit_type_id FK
        bigint price_cop "whole pesos, > 0"
        timestamptz observed_at
        date observed_on "day of observed_at in America/Bogota"
        varchar source "CHECK: manual or scraper"
        text source_url
        timestamptz created_at
    }
    scrape_runs {
        uuid id PK
        uuid developer_id FK
        date run_on
        timestamptz started_at
        timestamptz finished_at "nullable"
        varchar status "CHECK: running, succeeded, failed"
        int pages_fetched
        int pages_failed
        int observations_recorded
        text error "nullable"
        timestamptz created_at
        timestamptz updated_at
    }
    scraped_pages {
        uuid id PK
        uuid scrape_run_id FK
        text url "canonical URL, unique per run"
        smallint http_status
        char content_sha256
        text storage_key "raw HTML under data/raw/"
        timestamptz fetched_at
        timestamptz created_at
    }
    page_extractions {
        uuid id PK
        char content_sha256 "unique with model"
        text model "provider:model"
        int input_tokens
        int output_tokens
        jsonb payload "validated extraction"
        timestamptz created_at
    }
```

## Rules the database enforces

- **Price observations are append-only** (constitution, principle 2). A trigger on `price_observations` rejects `UPDATE` and `DELETE` per row, and `TRUNCATE` per statement, with `price_observations is append-only`. The table has no `updated_at`.
- **One observation per unit type per day:** unique (`unit_type_id`, `observed_on`). Because the table is append-only, a duplicate could not be removed later, so the use case checks first and a retry is not an error.
- **A unit type needs at least one area**, and any given area is greater than 0.
- **Row-level security is on** for every table, `alembic_version` included, with no policies. The Supabase REST API gets no access; the application connects as the table owner and is unaffected.
- **One extraction per HTML and model:** unique (`content_sha256`, `model`) in `page_extractions`, so an unchanged page is never sent to the model again, and switching models re-extracts instead of mixing results.
- **Municipality, source and scrape run status** are `varchar(16)` with a CHECK, not native Postgres enums, which are harder to change in a migration.

## Conventions

- Ids are UUIDs generated in the domain (`uuid4`), so an entity has an identity before it is saved.
- Prices are whole pesos in `bigint`. There are no cents and no float rounding.
- Prices are observed per unit type, not per project, so price per m² can be computed (week 4).
- Coordinates are written as `WKTElement("POINT(lon lat)", srid=4326)` and read with `ST_Y(geometry(location))` and `ST_X(geometry(location))`, without `shapely`.
- Local seed data lives in `seeds/projects.json` (copied by hand from public pages, no scraping). Load it with `uv run --env-file .env python -m sobreplano.interface.cli.seed`; it is idempotent.

## Not in the schema yet

Users and saved projects, pgvector embeddings, VIS/VIP classification, project stage, zones as polygons and project media (images, video, 3D models). Each arrives in its own spec.
