# SPEC 07 — API de lectura: detalle, histórico y filtros

> **Estado:** implementado
> **Depende de:** SPEC 03, SPEC 06
> **Fecha:** 2026-11-03
> **Objetivo:** Que la API responda "qué proyectos hay con estas condiciones, cuánto cuestan hoy y cuánto han subido desde el primer precio observado", con filtros en `GET /projects`, el detalle con histórico en `GET /projects/{slug}` y la lista de constructoras en `GET /developers`.

## Por qué existe este spec

El diferenciador de Sobreplano es mostrar cuánto ha subido cada proyecto desde su primer precio observado. Desde el SPEC 06 hay dos constructoras, unos 106 precios al día y, en Capital, observaciones desde el 28 de octubre. Pero la API del SPEC 03 solo lista proyectos con el último precio: no se puede filtrar, ni ver el histórico, ni saber cuánto subió algo.

El asesor del SPEC 08 va a usar estas consultas como herramientas (buscar, comparar, ver histórico), y el frontend del SPEC 11 como pantallas. Por eso las consultas viven en puertos del dominio y no solo en rutas HTTP.

Estado actual del repo (`main` en `5d7ef6b`):

- `src/sobreplano/interface/api/routes/projects.py:14-23`: `GET /projects` con `municipality`, `limit` y `offset`.
- `src/sobreplano/domain/ports.py:40-45`: `ProjectListingQuery.list_projects(municipality, limit, offset) -> ProjectPage`.
- `src/sobreplano/infrastructure/db/project_listing_query.py:73-105`: el último precio sale de `row_number() over (partition by unit_type_id order by observed_on desc)`, solo para las tipologías de la página.
- `src/sobreplano/domain/listings.py`: `LatestPrice`, `UnitTypeListing` (con `price_per_m2_cop` y `area_basis`), `ProjectListing` (con `location: GeoPoint | None` desde el SPEC 06) y `ProjectPage`.
- `src/sobreplano/interface/api/schemas.py:46-60`: `UnitTypeOut` con `latest_price`, `price_per_m2_cop` y `area_basis`.
- `tests/integration/test_api_query_budget.py:22`: `MAX_SELECTS = 3` para `GET /projects`.
- `CLAUDE.md`, secciones "FastAPI conventions" y "Migration rules".
- `projects.developer_id` y `unit_types.project_id` son llaves foráneas sin índice: Postgres no crea índices para las llaves foráneas.

## Alcance

**Dentro:**

- En cada tipología del listado y del detalle: primer precio observado y cambio porcentual desde ese primer precio, calculados con funciones de ventana.
- Filtros nuevos en `GET /projects`: `developer`, `min_price`, `max_price`, `min_bedrooms`, `min_area`, `max_area`; y orden `sort=name` (por defecto) o `sort=price`.
- `GET /projects/{slug}`: el proyecto con sus tipologías y el histórico de precios de cada una. `404` si el slug no existe.
- `GET /developers`: constructoras con su número de proyectos.
- Migración `0006`: índices en `projects.developer_id` y `unit_types.project_id`.
- Un presupuesto de consultas también para el detalle y para `/developers`.

**Fuera de alcance (para specs futuros):**

- Precio por m² agregado por zona o municipio: SPEC 14.
- Búsqueda por texto o por cercanía (radio en km): SPEC 14.
- Filtro por municipio múltiple, por estado de obra o por VIS.
- Caché HTTP, `ETag` y límite de peticiones: SPEC 10 y 12.
- Desplegar la API: SPEC 12.
- Vistas materializadas: cuando el volumen lo pida (ver Riesgos).

## Modelo de datos

### Migración `0006_fk_indexes`

- `op.create_index("ix_projects_developer_id", "projects", ["developer_id"])`.
- `op.create_index("ix_unit_types_project_id", "unit_types", ["project_id"])`.
- `price_observations.unit_type_id` ya está cubierto por el único (`unit_type_id`, `observed_on`), cuya primera columna es `unit_type_id`.

### Modelo de lectura (`domain/listings.py`)

```python
@dataclass(frozen=True)
class PricePoint:
    observed_on: date
    price_cop: int
    source: ObservationSource


@dataclass(frozen=True)
class UnitTypeListing:
    # campos actuales, más:
    first_price: PricePoint | None  # primera observación; None si no hay precios

    @property
    def change_since_first_pct(self) -> float | None: ...

    # (último - primero) / primero * 100, redondeado a 1 decimal.
    # None sin precio o si el primero y el último son el mismo día.


@dataclass(frozen=True)
class UnitTypeDetail:
    listing: UnitTypeListing
    history: list[PricePoint]  # todas las observaciones, de la más vieja a la más nueva


@dataclass(frozen=True)
class ProjectDetail:
    project: ProjectListing  # los mismos campos del listado
    unit_types: list[UnitTypeDetail]


@dataclass(frozen=True)
class DeveloperSummary:
    slug: str
    name: str
    website_url: str
    projects: int


class ProjectSort(StrEnum):
    NAME = "name"
    PRICE = "price"  # menor último precio entre las tipologías que cumplen los filtros


@dataclass(frozen=True)
class ProjectFilters:
    municipality: Municipality | None = None
    developer: str | None = None  # slug
    min_price: int | None = None
    max_price: int | None = None
    min_bedrooms: int | None = None
    min_area: Decimal | None = None
    max_area: Decimal | None = None
    # Valida: mínimos <= máximos y valores > 0; si no, DomainValidationError.
```

### Puertos (`domain/ports.py`)

```python
class ProjectListingQuery(Protocol):
    def list_projects(
        self, *, filters: ProjectFilters, sort: ProjectSort, limit: int, offset: int
    ) -> ProjectPage: ...

    def get_project(self, slug: str) -> ProjectDetail | None: ...

    def list_developers(self) -> list[DeveloperSummary]: ...
```

### Semántica de los filtros

- Los filtros de tipología (`min_price`, `max_price`, `min_bedrooms`, `min_area`, `max_area`) se aplican al **último precio** y al **área base** de cada tipología (privada si existe, si no construida: la misma regla de `price_per_m2_cop`).
- Un proyecto entra si **al menos una** tipología cumple todos los filtros de tipología a la vez.
- En la respuesta, el proyecto trae **solo las tipologías que cumplen**. Sin filtros de tipología, trae todas, como hoy.
- Una tipología sin precio no cumple ningún filtro de precio.
- `developer` es un slug; un slug desconocido da una lista vacía, no un error.
- `total` cuenta los proyectos que cumplen, sin paginar.
- `sort=price` ordena por el menor último precio de las tipologías que cumplen; los proyectos sin precio van al final; el desempate es por nombre y `id`.

### Consultas (`infrastructure/db/project_listing_query.py`)

Una CTE `latest_prices` con dos funciones de ventana sobre `price_observations`:

```sql
row_number()  over (partition by unit_type_id order by observed_on desc) as rank,
first_value(price_cop)   over (partition by unit_type_id order by observed_on) as first_price,
first_value(observed_on) over (partition by unit_type_id order by observed_on) as first_on
```

- **Listado:** como máximo 3 consultas, como hoy: el conteo, la página de proyectos (con `EXISTS` sobre las tipologías que cumplen) y las tipologías de la página con su último y primer precio.
- **Detalle:** como máximo 3 consultas: el proyecto con su constructora y su ubicación, sus tipologías con último y primer precio, y todas sus observaciones.
- **Constructoras:** 1 consulta con `count(projects.id)` agrupado.

### Contrato HTTP

`GET /projects?developer=constructora-capital&max_price=500000000&min_bedrooms=2&sort=price&limit=20`

- Parámetros nuevos opcionales; un `min_price` mayor que `max_price`, o un mínimo de área mayor que el máximo, da `422`.
- Cada tipología suma `first_price` (`{price_cop, observed_on, source}` o `null`) y `change_since_first_pct` (número o `null`).

`GET /projects/{slug}`

```json
{
  "id": "uuid", "slug": "axis-ciudad-peldar", "name": "AXIS - Ciudad Peldar",
  "developer": {"name": "Constructora Capital", "slug": "constructora-capital"},
  "municipality": "envigado", "neighborhood": "Las Vegas",
  "location": {"lat": 6.1735, "lon": -75.5925},
  "source_url": "https://...",
  "unit_types": [
    {
      "...": "los campos del listado",
      "first_price": {"price_cop": 716500000, "observed_on": "2026-10-28", "source": "manual"},
      "change_since_first_pct": 0.0,
      "history": [
        {"observed_on": "2026-10-28", "price_cop": 716500000, "source": "manual"},
        {"observed_on": "2026-11-03", "price_cop": 716500000, "source": "scraper"}
      ]
    }
  ]
}
```

- `404 {"detail": "project not found"}` con `raise HTTPException(status_code=404, ...)`.
- El slug se valida con `Path(pattern="^[a-z0-9-]{1,80}$")`; otro formato da `422`.

`GET /developers` → `[{"slug": "...", "name": "...", "website_url": "...", "projects": 25}]`, ordenado por nombre.

## Plan de implementación

1. **Índices.** Migración `0006` con los dos índices. `upgrade`, `downgrade -1` y `upgrade` en local; `alembic check` limpio. Commit `feat:`.
2. **Dominio.** `PricePoint`, `first_price` y `change_since_first_pct` en `UnitTypeListing`; `UnitTypeDetail`, `ProjectDetail`, `DeveloperSummary`, `ProjectSort` y `ProjectFilters` con su validación. Tests unitarios del porcentaje (sube, baja, igual, un solo día, sin precio) y de los filtros inválidos. Commit `feat:`.
3. **Primer precio en el listado.** La CTE con `first_value` en `project_listing_query.py`; el listado actual sigue con 3 consultas y suma `first_price`. Test de integración con tres días de precios de una tipología. Commit `feat:`.
4. **Filtros y orden.** `list_projects` con `ProjectFilters` y `ProjectSort`; `EXISTS` sobre las tipologías que cumplen; solo esas en la respuesta. Tests de integración: cada filtro solo, la combinación, sin precio, `sort=price` con proyectos sin precio al final, y `total` correcto. Commit `feat:`.
5. **Detalle y constructoras.** `get_project` y `list_developers` en la consulta SQL. Tests de integración, incluido un proyecto sin ubicación. Commit `feat:`.
6. **Rutas.** Parámetros nuevos en `GET /projects` (con `Annotated` y `Query`), `GET /projects/{slug}` y `GET /developers`; esquemas en `schemas.py`. Tests con `TestClient` y `dependency_overrides`: contrato, `404`, `422` por filtros inválidos y por slug mal formado. Commit `feat:`.
7. **Presupuesto de consultas.** Ampliar `test_api_query_budget.py`: listado con todos los filtros, 3 o menos; detalle, 3 o menos; `/developers`, 1. Commit `test:`.
8. **Documentación y migración en la nube.** README con ejemplos de `curl` de los tres endpoints; `CLAUDE.md` con las rutas. `alembic upgrade head` en la nube por el pooler en modo sesión, fuera de 5:45–6:45. Commit `docs:`.

## Criterios de aceptación

Cada criterio se verifica pegando el comando y su salida en el PR (constitución, principio 6).

- [ ] `alembic upgrade head`, `downgrade -1` y `upgrade head` en local; `alembic check` limpio; una sola cabeza; la nube en `0006`.
- [ ] Con la API apuntando a la nube, `curl -s localhost:8000/projects/axis-ciudad-peldar | jq '.unit_types[] | select(.name == "Tipo 02") | .history | length'` es al menos 2 (precio manual del 28 oct y del scraper).
- [ ] En esa misma tipología, `first_price.source` es `manual` y `first_price.observed_on` es `2026-10-28`.
- [ ] `curl -s localhost:8000/projects/no-existe -o /dev/null -w "%{http_code}"` imprime `404`, y `curl -s "localhost:8000/projects/NO_VALIDO" -o /dev/null -w "%{http_code}"` imprime `422`.
- [ ] `curl -s "localhost:8000/projects?developer=constructora-capital" | jq '[.items[].developer.slug] | unique'` devuelve solo `constructora-capital`.
- [ ] `curl -s "localhost:8000/projects?max_price=400000000&sort=price" | jq '[.items[].unit_types[].latest_price.price_cop] | max'` es menor o igual que 400.000.000, y el primer proyecto es el más barato.
- [ ] `curl -s "localhost:8000/projects?min_price=900000000&max_price=100000000" -o /dev/null -w "%{http_code}"` imprime `422`.
- [ ] `curl -s localhost:8000/developers | jq 'length'` imprime `2`, y la suma de `projects` coincide con `total` de `GET /projects` sin filtros.
- [ ] El test de presupuesto pasa: listado con todos los filtros en 3 consultas o menos, detalle en 3 o menos, `/developers` en 1.
- [ ] Las convenciones de FastAPI siguen: `grep -rn "return HTTPException" src` vacío, `grep -rnE "= Depends\(" src` vacío, `async def` solo en el lifespan.
- [ ] `uv run pytest -m "not integration"`, `uv run pyright` (0 errores) y `uv run lint-imports` (2 contratos) pasan; el CI del PR queda en verde.

## Decisiones tomadas y descartadas

- **Sí:** primer precio y cambio porcentual en cada tipología del listado. Es el diferenciador del proyecto y sale de la misma CTE, sin consultas extra.
- **Sí:** `first_value` en SQL para el primer precio y el cálculo del porcentaje en el dominio. La base de datos encuentra el primer punto; la regla de negocio (redondeo, `None` si es el mismo día) se prueba sin base de datos.
- **No:** guardar el primer precio en una columna. Se puede derivar siempre del histórico, que es append-only, y una copia podría desincronizarse.
- **Sí:** el cambio en porcentaje, no en pesos por día. Es lo que se entiende de un vistazo y lo que se compara entre proyectos de precios muy distintos.
- **Sí:** los filtros de tipología se cumplen todos en la misma tipología, y la respuesta trae solo las que cumplen. "Dos alcobas por menos de 400 millones" debe encontrar un apartamento que tenga las dos cosas, no un proyecto con uno barato de una alcoba y otro caro de dos.
- **Sí:** el área de los filtros es el área base (privada, si no construida), la misma del precio por m². **No:** filtrar por un área distinta de la que se muestra.
- **Sí:** `sort=price` con los proyectos sin precio al final. **No:** más órdenes (por subida, por precio por m²) hasta que el frontend o el asesor los pidan.
- **Sí:** el histórico completo dentro del detalle. Con una observación por tipología y día son unas 365 filas por tipología al año; cabe en una respuesta. **No:** un endpoint aparte de histórico con paginación todavía.
- **Sí:** un `developer` desconocido da lista vacía. Las constructoras cambian y la lista sale de `/developers`; un `422` no ayuda más que una lista vacía.
- **Sí:** validar el formato del slug en la ruta. Corta entradas absurdas antes de la base de datos y documenta el formato en OpenAPI.
- **Sí:** índices en las dos llaves foráneas que filtran y unen las consultas nuevas. El asesor de seguridad de Supabase marca las llaves foráneas sin índice.
- **Sí:** las consultas detrás del puerto `ProjectListingQuery`, no en las rutas. El asesor del SPEC 08 las va a usar como herramientas sin pasar por HTTP.

## Riesgos identificados

| Riesgo | Mitigación |
| --- | --- |
| La CTE de últimos precios recorre todas las observaciones para filtrar por precio, y crece cada día | Hoy son unas 100 filas por día. Se mide con `EXPLAIN ANALYZE` en el PR; si pasa de 50 ms, una vista materializada que se refresca después de cada corrida |
| `first_value` sin marco explícito devuelve un valor distinto del esperado | Con `order by observed_on` y sin marco, el primer valor de la partición es siempre la primera fila; un test con tres días lo verifica |
| La semilla de Capital tiene la misma tipología con precio manual y del scraper el mismo día | No puede pasar: el único (`unit_type_id`, `observed_on`) lo impide desde el SPEC 02 |
| Filtrar las tipologías de la respuesta confunde al frontend, que espera ver todas | El contrato lo dice en OpenAPI; sin filtros de tipología la respuesta no cambia |

## Lo que **no** entra en este spec

- Precio por m² por zona y búsqueda por cercanía.
- Filtros por varios municipios, estado de obra o VIS.
- Caché HTTP, `ETag` y límite de peticiones.
- Despliegue de la API.
- Vistas materializadas.

Cada uno, si llega, va en su propio spec.
