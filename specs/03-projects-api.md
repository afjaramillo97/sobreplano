# SPEC 03 — API de proyectos con último precio y precio por m²

> **Estado:** aprobado
> **Depende de:** SPEC 01, SPEC 02
> **Fecha:** 2026-10-29
> **Objetivo:** Exponer con FastAPI `GET /health` y `GET /projects`, que lista los proyectos con el último precio y el precio por m² de cada tipología, en tres consultas SQL como máximo.

## Por qué existe este spec

SPEC 02 dejó los datos guardados, pero solo se pueden ver con `psql`. Este spec abre la primera puerta de lectura. La usarán el frontend (semana 7), el asesor (semana 5, como herramienta de búsqueda) y un reclutador que abra `/docs`. También fija cómo se arma la app (fábrica, lifespan, sesión por request, configuración) antes de que lleguen más endpoints.

Estado actual del repo (confirmado antes de escribir, rama `main` en `97549d6`):

- `src/sobreplano/interface/` solo tiene `cli/` (la semilla). No existe `interface/api/`.
- `src/sobreplano/domain/ports.py:11-27` define `CatalogRepository` y `PriceObservationRepository`. Ninguno sirve para un listado: devuelven entidades sueltas, y armar la respuesta con ellos sería una consulta por proyecto y otra por tipología (N+1).
- `src/sobreplano/infrastructure/db/catalog_repository.py:13-14` ya resuelve lat y lon con `ST_Y`/`ST_X`. El listado reutiliza ese patrón.
- `price_observations` tiene la restricción única (`unit_type_id`, `observed_on`) desde la migración `0001`. Por eso el último precio es el de `observed_on` más reciente, y ese índice sirve para encontrarlo.
- `src/sobreplano/infrastructure/db/engine.py:9` lee `DATABASE_URL` directo de `os.environ`.
- `tests/integration/conftest.py:27-38` tiene el fixture `session` con una transacción revertida por test. Los tests de la API lo reutilizan.
- Ajustes pendientes de SPEC 02: `migrations/versions/0001_schema_v1.py:241` borra PostGIS en el `downgrade`; `migrations/env.py:1` y `:3` y `0001_schema_v1.py:1` tienen comentarios de Pylint y pyright que no aplican.
- `pyproject.toml:7-13` no incluye `fastapi` ni `pydantic-settings`.

## Alcance

**Dentro:**

- Ajustes heredados de SPEC 02 (primer paso del plan).
- Dependencias `fastapi[standard]` y `pydantic-settings`.
- Configuración con `pydantic-settings` en `infrastructure/settings.py`, como única fuente de `DATABASE_URL`.
- Modelo de lectura en el dominio (`domain/listings.py`), con la regla del precio por m².
- Puerto `ProjectListingQuery` en `domain/ports.py` y su implementación SQL en `infrastructure/db/project_listing_query.py`.
- App FastAPI en `interface/api/`: fábrica `create_app()`, lifespan con el motor, sesión por request, `GET /health` y `GET /projects`.
- `GET /projects` con filtro opcional por municipio y paginación `limit`/`offset`.
- Tests unitarios de la regla del precio por m² y tests de integración de la API con `TestClient`.
- Skill oficial de FastAPI (`uvx library-skills --claude`), auditado antes de usarlo.
- README con una sección "Run locally"; `CLAUDE.md` con los comandos de la API.

**Fuera de alcance (para specs futuros):**

- Detalle de un proyecto (`GET /projects/{slug}`) e histórico de precios: semana 4.
- Precio por m² agregado por zona o municipio: semana 4.
- Filtros por precio, habitaciones, área o constructora, y ordenar por precio.
- CORS, autenticación y límite de peticiones: semana 7.
- Despliegue de la API (Lambda, Render o contenedor) y Docker.
- Endpoints de escritura: los datos solo entran por la semilla y los scrapers.
- tRPC y el BFF del frontend.

## Modelo de datos

Este spec no cambia el esquema ni agrega migraciones. Agrega un modelo de lectura y un contrato HTTP.

### Modelo de lectura (`src/sobreplano/domain/listings.py`)

```python
@dataclass(frozen=True)
class LatestPrice:
    price_cop: int
    observed_on: date
    source: ObservationSource


class AreaBasis(StrEnum):
    PRIVATE = "private"
    BUILT = "built"


@dataclass(frozen=True)
class UnitTypeListing:
    id: UUID
    name: str
    private_area_m2: Decimal | None
    built_area_m2: Decimal | None
    bedrooms: int
    bathrooms: int
    latest_price: LatestPrice | None  # None si la tipología no tiene observaciones

    @property
    def area_basis(self) -> AreaBasis: ...  # PRIVATE si hay área privada; si no, BUILT
    @property
    def price_per_m2_cop(self) -> int | None: ...  # round(price_cop / área base); None sin precio


@dataclass(frozen=True)
class ProjectListing:
    id: UUID
    slug: str
    name: str
    developer_name: str
    developer_slug: str
    municipality: Municipality
    neighborhood: str | None
    location: GeoPoint
    source_url: str
    unit_types: list[UnitTypeListing]  # ordenadas por nombre


@dataclass(frozen=True)
class ProjectPage:
    items: list[ProjectListing]  # ordenados por nombre de proyecto
    total: int  # total con el filtro aplicado, sin paginar
```

### Puerto (`src/sobreplano/domain/ports.py`)

```python
class ProjectListingQuery(Protocol):
    def list_projects(
        self, *, municipality: Municipality | None, limit: int, offset: int
    ) -> ProjectPage: ...
```

La implementación (`SqlProjectListingQuery`) hace tres consultas como máximo:

1. `count(*)` de proyectos con el filtro.
2. La página de proyectos, unida a `developers`, con lat y lon por `ST_Y`/`ST_X`.
3. Las tipologías de esos proyectos, unidas por `LEFT JOIN` a una subconsulta con `row_number() OVER (PARTITION BY unit_type_id ORDER BY observed_on DESC)`, quedándose con la fila 1.

Si la página viene vacía, la consulta 3 no se ejecuta.

### Contrato HTTP

`GET /health`

- `200 {"status": "ok", "database": "ok"}` si `SELECT 1` responde.
- `503 {"status": "degraded", "database": "unavailable"}` si la base de datos falla.

`GET /projects?municipality=envigado&limit=50&offset=0`

- `municipality`: opcional, uno de los 10 valores de `Municipality`. Otro valor da `422`.
- `limit`: 1 a 100, por defecto 50. `offset`: 0 o más, por defecto 0. Fuera de rango da `422`.

```json
{
  "items": [
    {
      "id": "uuid", "slug": "axis-ciudad-peldar", "name": "AXIS - Ciudad Peldar",
      "developer": {"name": "Constructora Capital", "slug": "constructora-capital"},
      "municipality": "envigado", "neighborhood": "Las Vegas",
      "location": {"lat": 6.1735, "lon": -75.5925},
      "source_url": "https://...",
      "unit_types": [
        {
          "id": "uuid", "name": "Tipo 02",
          "private_area_m2": 54.98, "built_area_m2": 60.67,
          "bedrooms": 1, "bathrooms": 2,
          "latest_price": {"price_cop": 716500000, "observed_on": "2026-10-28", "source": "manual"},
          "price_per_m2_cop": 13032012, "area_basis": "private"
        }
      ]
    }
  ],
  "total": 3, "limit": 50, "offset": 0
}
```

Los modelos Pydantic de la respuesta viven en `interface/api/schemas.py`. Las áreas salen como número (`float`), no como texto.

## Plan de implementación

1. **Ajustes de SPEC 02.** Quitar `DROP EXTENSION IF EXISTS postgis` del `downgrade` de `0001`; quitar los `# pylint: skip-file`; quitar `# pyright: basic` de `migrations/env.py`, porque pyright no incluye `migrations/`. `alembic upgrade head`, `downgrade base` y otra vez `upgrade head` siguen funcionando. Commit `chore:`.
2. **Dependencias y skill.** `uv add "fastapi[standard]" pydantic-settings`. Agregar `"ASYNC"` al `select` de ruff, para detectar llamadas bloqueantes dentro de `async def`. Auditar y correr `uvx library-skills --claude`. Commit `chore:`.
3. **Configuración.** `infrastructure/settings.py` con `Settings(BaseSettings)` y el campo `database_url`; `load_settings()` es el único lugar con `# pyright: ignore[reportCallIssue]`, con un comentario del porqué. `engine.get_database_url()` pasa a usar `load_settings()` y mantiene el mismo mensaje de error. Los comandos siguen usando `uv run --env-file .env`. Commit `refactor:`.
4. **Modelo de lectura.** `domain/listings.py` y el puerto `ProjectListingQuery`, con tests unitarios en `tests/unit/domain/test_listings.py`: base privada, respaldo a construida, sin precio y redondeo. Commit `feat:`.
5. **Consulta SQL.** Primero, mover las expresiones de coordenadas (`_LAT`, `_LON` y el armado de `WKTElement("POINT(lon lat)")`, hoy en `catalog_repository.py:13-14` y `:73`) a `infrastructure/db/geo.py`, y usarlas desde los dos repositorios. Así el orden longitud/latitud vive en un solo lugar. Después, `infrastructure/db/project_listing_query.py` con las tres consultas. Tests de integración: último precio cuando hay dos días, tipología sin precio, filtro por municipio, `total` y paginación. Commit `feat:`.
6. **App y salud.** `interface/api/main.py` con `create_app()` y un lifespan que crea el motor una sola vez, guarda el `sessionmaker` en `app.state` y cierra el motor al apagar. `interface/api/dependencies.py` con `get_session` (toma el `sessionmaker` de `app.state`, una sesión por request, sin commit), `get_project_listing_query` y los alias `SessionDep = Annotated[Session, Depends(get_session)]` y `ListingQueryDep`. `interface/api/routes/health.py` recibe `response: Response` y fija `response.status_code = 503` cuando falla la base de datos; no usa `HTTPException`, porque su cuerpo sería `{"detail": ...}` y rompería el contrato. Test del `503` con `app.dependency_overrides[get_session]` apuntando a una sesión sobre una URL inalcanzable (`127.0.0.1:1`), que produce un `OperationalError` real. Commit `feat:`.
7. **Listado.** `interface/api/schemas.py` y `interface/api/routes/projects.py`. Tests de integración con `TestClient` y `app.dependency_overrides[get_session]` apuntando al fixture de sesión transaccional. Sin `unittest.mock`. Commit `feat:`.
8. **Presupuesto de consultas.** Test de integración que cuenta las sentencias con el evento `before_cursor_execute` de SQLAlchemy y exige 3 o menos en `GET /projects`, con al menos 2 proyectos y 2 tipologías cada uno. Commit `test:`.
9. **Documentación.** README con "Run locally" (Supabase, migraciones, semilla, `uvicorn`, `/docs`); `CLAUDE.md` con el comando de la API, `interface/api/` en el layout y una sección "FastAPI conventions" con las cinco reglas de FastAPI de la sección de decisiones (endpoints `def`, motor en el lifespan, `Annotated`, `raise HTTPException`, `dependency_overrides`), para que los endpoints futuros las sigan. Además, una sección "Migration rules" con las reglas de Alembic de la sección de decisiones, para el próximo spec que toque el esquema. Commit `docs:`.

Cada paso deja los controles en verde y se puede commitear solo.

## Criterios de aceptación

Cada criterio se verifica pegando el comando y su salida en el PR (constitución, principio 6).

- [ ] `uv run --env-file .env uvicorn sobreplano.interface.api.main:app` arranca y `curl -s localhost:8000/health` devuelve `{"status":"ok","database":"ok"}`.
- [ ] Con la base de datos apagada (`supabase db stop`), `curl -i localhost:8000/health` devuelve `503`.
- [ ] Con la semilla cargada, `curl -s "localhost:8000/projects" | jq '.total, (.items | length)'` imprime `3` y `3`.
- [ ] `curl -s "localhost:8000/projects?municipality=envigado" | jq .total` imprime `3`, y con `municipality=bello` imprime `0`.
- [ ] `curl -s -o /dev/null -w "%{http_code}" "localhost:8000/projects?municipality=nope"` imprime `422`; con `limit=101` también.
- [ ] Para "Tipo 02" de AXIS, `price_per_m2_cop` es `round(716500000 / 54.98)` y `area_basis` es `private`.
- [ ] `curl -s localhost:8000/openapi.json | jq '.paths | keys'` muestra `/health` y `/projects`, y `/docs` abre en el navegador.
- [ ] El test de presupuesto de consultas pasa: `GET /projects` ejecuta 3 sentencias o menos.
- [ ] `uv run pytest -m "not integration"` pasa sin base de datos y `uv run --env-file .env pytest` pasa completo.
- [ ] `uv run pyright` termina con 0 errores, con un solo `pyright: ignore` en `src/` (`grep -rn "pyright: ignore" src` lo muestra).
- [ ] `uv run lint-imports` reporta 2 contratos cumplidos.
- [ ] `grep -rn "pylint\|pyright: basic\|DROP EXTENSION" migrations` no devuelve nada.
- [ ] Convenciones de FastAPI, cada una con su comando:
  - `grep -rn "async def" src/sobreplano/interface/api` solo muestra el lifespan.
  - `grep -rn "return HTTPException" src` no devuelve nada.
  - `grep -rnE "= Depends\(" src` no devuelve nada (todas las dependencias usan `Annotated`).
  - `grep -rn "create_db_engine\|create_engine" src/sobreplano/interface/api` solo aparece en `main.py`, dentro del lifespan.
  - `grep -rn "unittest.mock\|from unittest import mock" tests` no devuelve nada.
  - `uv run ruff check` pasa con la regla `ASYNC` activa.
- [ ] `grep -rn "ST_Y\|ST_X\|POINT(" src --include=*.py` solo muestra `infrastructure/db/geo.py`.
- [ ] `CLAUDE.md` tiene las secciones "FastAPI conventions" y "Migration rules".
- [ ] El CI del PR queda en verde (enlace a la ejecución).

## Decisiones tomadas y descartadas

- **Sí:** un modelo de lectura propio (`ProjectListing`) con su puerto `ProjectListingQuery`. **No:** armar el listado con los repositorios de SPEC 02, que obligaría a N+1 consultas.
- **Sí:** el precio por m² como propiedad del dominio (`UnitTypeListing`). Es una regla de negocio (área privada primero), se prueba sin base de datos y la reutilizan el asesor y la semana 4.
- **No:** un caso de uso `ListProjects` en `application/`. Hoy solo pasaría los parámetros a la consulta; la regla vive en el dominio. Entra cuando haya lógica que orquestar.
- **Sí:** último precio por `observed_on DESC` con `row_number()`. Como hay una observación por día, el día más reciente es el último precio, y la restricción única (`unit_type_id`, `observed_on`) sirve de índice. **No:** `DISTINCT ON`, que es específico de Postgres. Además, en SQLAlchemy 2.1 `select(...).distinct(col)` lanza `SADeprecationWarning` y pide la extensión `postgresql.distinct_on` (probado el 29 oct). `row_number()` es SQL estándar y adelanta el tema de funciones de ventana de la semana 4.
- **Sí:** tres consultas como máximo, verificadas con un test. Así una regresión a N+1 rompe el CI y no pasa en silencio.
- **Sí:** `limit` (1 a 100, por defecto 50) y `offset`, con `total`. Con los scrapers habrá cientos de proyectos; agregar paginación después cambiaría el contrato.
- **Sí:** filtro solo por municipio. Los demás filtros llegan cuando el frontend o el asesor los pidan.
- **Sí:** áreas como número en el JSON. Pydantic serializa `Decimal` como texto por defecto, y un cliente esperaría números.
- **Sí:** `pydantic-settings` como única fuente de `DATABASE_URL`, también para Alembic y la semilla. **No:** que lea `.env` por su cuenta; se mantiene `uv run --env-file .env` para no cambiar los comandos de SPEC 02.
- **Sí:** un único `# pyright: ignore[reportCallIssue]` en `load_settings()`. Pyright estricto no sabe que `BaseSettings()` llena `database_url` desde el entorno (probado el 29 oct con pydantic-settings 2.16.2).
- **Sí:** lifespan con `AsyncGenerator[None]`. Anotarlo como `AsyncIterator` está marcado como obsoleto y pyright estricto lo rechaza (probado el 29 oct).
- **Sí:** fábrica `create_app()`. Los tests crean la app con su propia configuración y cambian dependencias sin variables globales.
- **Sí:** SQLAlchemy síncrono con endpoints `def`, nunca `async def`. FastAPI corre los `def` en un pool de hilos; una llamada síncrona dentro de `async def` bloquearía el event loop de Uvicorn y con él todas las peticiones. El lifespan es la única función `async`, y no hace I/O bloqueante: `create_engine` no abre conexiones. La regla `ASYNC` de ruff detecta llamadas bloqueantes conocidas (`time.sleep`, clientes HTTP síncronos) dentro de `async def`.
- **Sí:** el motor se crea una sola vez en el lifespan y las peticiones solo abren sesiones del `sessionmaker` guardado en `app.state`. **No:** crear el motor dentro de `get_session`; cada petición abriría su propio pool y agotaría las conexiones de Supabase.
- **Sí:** dependencias declaradas con `Annotated` y alias reutilizables (`SessionDep`, `ListingQueryDep`). **No:** la forma antigua `session: Session = Depends(get_session)`.
- **Sí:** los errores HTTP se lanzan con `raise HTTPException(...)`, nunca con `return`: un `return` respondería `200` con la excepción serializada. `/health` es la excepción documentada: su `503` es parte del contrato, así que fija `response.status_code` y devuelve el cuerpo acordado.
- **Sí:** en los tests se cambian dependencias con `app.dependency_overrides`. **No:** `unittest.mock` para simular sesiones o consultas; el `503` se prueba con un `OperationalError` real contra una URL inalcanzable.
- **Sí:** una sesión por request que nunca hace commit. La API solo lee.
- **Sí:** `/health` revisa la base de datos y responde `503` si falla. **No:** separar liveness y readiness; no hay orquestador que los use.
- **Sí:** `fastapi[standard]`, que trae `uvicorn` y `httpx` para `TestClient`.
- **Sí:** un solo módulo (`infrastructure/db/geo.py`) para escribir y leer coordenadas. PostGIS usa (x, y) = (longitud, latitud), al revés de como se suelen escribir; con dos copias del código, la tercera consulta geográfica (distancias, semana 5) tendría tres oportunidades de invertirlas.
- **Sí:** reglas de Alembic escritas en `CLAUDE.md` aunque este spec no cree migraciones, para el próximo que toque el esquema (`scrape_runs`, semana 3):
  - Revisar a mano cada `--autogenerate` antes de `upgrade`. Alembic no detecta renombres: los ve como borrar y crear la columna, y se pierden los datos. Los renombres se escriben con `op.alter_column(..., new_column_name=...)` o `op.rename_table`.
  - Cambiar la expresión de un `CheckConstraint` no genera migración, porque Alembic los compara por nombre. Se escribe a mano: borrar el CHECK viejo y crear el nuevo.
  - `CREATE EXTENSION`, triggers, funciones y RLS no los detecta `--autogenerate`; se agregan a mano y siempre con `WITH SCHEMA extensions` para las extensiones.
  - La nulabilidad sale solo del tipo (`Mapped[T]` es `NOT NULL`, `Mapped[T | None]` es `NULL`); no se usa `nullable=` en los modelos.
  - Nunca `supabase db diff` ni `supabase/migrations/`: Alembic es el único dueño del esquema. Por eso `supabase stop --no-backup` es seguro en local: el esquema se reconstruye con `alembic upgrade head` y los datos con la semilla.

## Riesgos identificados

| Riesgo | Mitigación |
| --- | --- |
| El `LEFT JOIN` con la subconsulta de ventana recorre todas las observaciones a medida que crece el histórico | Se filtra por los `unit_type_id` de la página dentro de la subconsulta. Se revisa con `EXPLAIN` en la semana 4, cuando haya histórico real |
| `TestClient` corre el lifespan y crea un motor real aunque el test cambie la sesión | Los tests pasan a `create_app()` una configuración con la `DATABASE_URL` de pruebas; el motor no hace ninguna consulta si nadie lo usa |
| El conteo de consultas incluye sentencias de la sesión que no son del listado (`BEGIN`, `SAVEPOINT`) | El contador solo suma sentencias que empiezan por `SELECT` |
| El skill de FastAPI trae instrucciones que chocan con la constitución (por ejemplo, SQLModel) | Se audita antes de instalar; si choca, manda la constitución y se documenta en el PR |
| La semilla tiene un solo municipio, así que el filtro casi no se prueba con datos reales | Los tests de integración crean proyectos en dos municipios con sus fixtures |

## Lo que **no** entra en este spec

- Detalle de proyecto e histórico de precios.
- Precio por m² por zona.
- Filtros por precio, habitaciones, área o constructora.
- CORS, autenticación y límite de peticiones.
- Despliegue, Docker y endpoints de escritura.
- tRPC y el BFF.

Cada uno, si llega, va en su propio spec.
