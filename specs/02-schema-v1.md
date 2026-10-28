# SPEC 02 — Esquema v1 y repositorio de precios append-only

> **Estado:** aprobado
> **Depende de:** SPEC 01
> **Fecha:** 2026-10-28
> **Objetivo:** Persistir constructoras, proyectos, tipologías y observaciones de precio en Postgres (Supabase local) con Alembic, de forma que la base de datos misma impida modificar o borrar una observación de precio.

## Por qué existe este spec

El diferenciador de Sobreplano es el histórico de precios: cuánto ha subido cada proyecto desde el primer precio observado. Ese histórico solo vale si nadie lo puede reescribir. La constitución lo exige en el principio 2, pero hoy no existe ni el esquema ni el código que lo cumpla.

Estado actual del repo (confirmado antes de escribir, rama `main` en `e2d05e4`):

- `pyproject.toml:7` tiene `dependencies = []`: el paquete aún no depende de nada.
- `pyproject.toml:48-49`: el contrato `forbidden` solo prohíbe `sqlalchemy` y `fastapi` en `domain` y `application`.
- Las cuatro capas en `src/sobreplano/` solo tienen `__init__.py` vacíos. `tests/test_layers.py` es el único test.
- `.github/workflows/ci.yml:18-28` corre `uv sync --locked` y los cinco controles del SPEC 01, sin base de datos.
- `CLAUDE.md:36` planea `migrations/` en la raíz para Alembic.
- `docs/constitution.md:19` verifica el principio 2 con un `grep` de `UPDATE|DELETE`, que choca con el trigger de este spec (ver Decisiones).
- `.gitignore:232` ignora `data/`, así que la semilla no puede vivir ahí.
- No existen `supabase/`, `migrations/`, `alembic.ini` ni `.env.example`.

## Alcance

**Dentro:**

- Supabase local con su CLI (`supabase init`, `supabase db start`), versionando `supabase/config.toml`.
- Dependencias de runtime: `sqlalchemy`, `geoalchemy2`, `psycopg[binary]`, `alembic` y `pydantic`.
- Entidades de dominio y puertos en `src/sobreplano/domain/`, sin frameworks.
- Caso de uso `RecordPriceObservation` en `src/sobreplano/application/`.
- Modelos SQLAlchemy, motor y dos repositorios en `src/sobreplano/infrastructure/db/`.
- Alembic en `migrations/` con una migración `0001_schema_v1`: PostGIS, cuatro tablas, RLS activado y trigger append-only.
- Semilla de 3 proyectos reales del Valle de Aburrá en `seeds/projects.json`, cargada con `uv run python -m sobreplano.interface.cli.seed`.
- Tests unitarios (dominio y caso de uso, sin base de datos) y de integración (marcados `integration`, contra Postgres).
- CI: Postgres de Supabase, `alembic upgrade head`, `alembic check`, una sola cabeza y tests de integración.
- Plugin `postgres-best-practices` de Supabase, auditado y habilitado en `.claude/settings.json`.
- Constitución v1.1.0 (verificación del principio 2), `docs/schema.md` con el diagrama del esquema y `CLAUDE.md` al día.

**Fuera de alcance (para specs futuros):**

- Proyecto de Supabase en la nube: llega con el primer scraper que escriba desde Lambda (semana 3).
- Tabla `scrape_runs` y la relación de cada observación con su corrida: spec de scrapers.
- Consulta del último precio por tipología y cualquier endpoint: SPEC 03.
- Usuarios, autenticación, proyectos guardados y alertas.
- pgvector, embeddings y búsqueda híbrida: semana 5.
- Clasificación VIS/VIP, etapa del proyecto (preventa, obra, entregado) y zonas como polígonos.
- SQLAlchemy asíncrono y `pydantic-settings`.
- MCP de Supabase.

## Modelo de datos

### Dominio (`src/sobreplano/domain/`)

Dataclasses congeladas con validación en `__post_init__`. Los ids son `UUID` generados en el dominio (`uuid4`), así una entidad tiene identidad antes de guardarse.

```python
# catalog.py
class Municipality(StrEnum):
    MEDELLIN = "medellin"; BELLO = "bello"; ITAGUI = "itagui"; ENVIGADO = "envigado"
    SABANETA = "sabaneta"; LA_ESTRELLA = "la_estrella"; CALDAS = "caldas"
    COPACABANA = "copacabana"; GIRARDOTA = "girardota"; BARBOSA = "barbosa"

@dataclass(frozen=True)
class GeoPoint:
    lat: float  # 5.95 <= lat <= 6.60: Valle de Aburrá
    lon: float  # -75.80 <= lon <= -75.20

@dataclass(frozen=True)
class Developer:
    id: UUID; name: str; slug: str; website_url: str

@dataclass(frozen=True)
class Project:
    id: UUID; developer_id: UUID; name: str; slug: str
    municipality: Municipality; neighborhood: str | None
    location: GeoPoint; source_url: str

@dataclass(frozen=True)
class UnitType:
    id: UUID; project_id: UUID; name: str
    private_area_m2: Decimal | None; built_area_m2: Decimal | None  # al menos una
    bedrooms: int; bathrooms: int

# pricing.py
class ObservationSource(StrEnum):
    MANUAL = "manual"; SCRAPER = "scraper"

@dataclass(frozen=True)
class PriceObservation:
    id: UUID; unit_type_id: UUID; price_cop: int  # pesos enteros, > 0
    observed_at: datetime  # con zona horaria
    observed_on: date      # fecha de observed_at en America/Bogota
    source: ObservationSource; source_url: str
```

Las violaciones lanzan `DomainValidationError` (`errors.py`).

### Puertos (`src/sobreplano/domain/ports.py`)

```python
class CatalogRepository(Protocol):
    def add_developer(self, developer: Developer) -> None: ...
    def get_developer_by_slug(self, slug: str) -> Developer | None: ...
    def add_project(self, project: Project) -> None: ...
    def get_project_by_slug(self, slug: str) -> Project | None: ...
    def add_unit_type(self, unit_type: UnitType) -> None: ...
    def list_unit_types(self, project_id: UUID) -> list[UnitType]: ...

class PriceObservationRepository(Protocol):
    def add(self, observation: PriceObservation) -> None: ...
    def exists_for_day(self, unit_type_id: UUID, observed_on: date) -> bool: ...
    def list_by_unit_type(self, unit_type_id: UUID) -> list[PriceObservation]: ...
```

`PriceObservationRepository` no tiene `update` ni `delete`. Los repositorios no hacen commit: lo hace quien abre la sesión.

### Tablas (`migrations/versions/0001_schema_v1.py`)

| Tabla | Columnas | Restricciones |
| --- | --- | --- |
| `developers` | `id uuid`, `name text`, `slug text`, `website_url text`, `created_at`, `updated_at` | `slug` único |
| `projects` | `id`, `developer_id` → `developers`, `name`, `slug`, `municipality varchar(16)`, `neighborhood text null`, `location geography(POINT, 4326)`, `source_url`, `created_at`, `updated_at` | `slug` único; `municipality` con CHECK de los 10 valores; índice GIST en `location` |
| `unit_types` | `id`, `project_id` → `projects`, `name`, `private_area_m2 numeric(7,2) null`, `built_area_m2 numeric(7,2) null`, `bedrooms smallint`, `bathrooms smallint`, `created_at`, `updated_at` | único (`project_id`, `name`); CHECK: al menos un área no nula y áreas > 0 |
| `price_observations` | `id`, `unit_type_id` → `unit_types`, `price_cop bigint`, `observed_at timestamptz`, `observed_on date`, `source varchar(16)`, `source_url text`, `created_at` | único (`unit_type_id`, `observed_on`); CHECK `price_cop > 0`; CHECK de `source`; sin `updated_at` |

Además, en la misma migración:

- `CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA extensions;`
- `ENABLE ROW LEVEL SECURITY` en las cuatro tablas y en `alembic_version`, sin políticas. La API REST de Supabase queda sin acceso y la aplicación, que se conecta como dueña de las tablas, no se ve afectada.
- Función `prevent_price_observation_changes()` con dos triggers sobre `price_observations`: `BEFORE UPDATE OR DELETE ... FOR EACH ROW` y `BEFORE TRUNCATE ... FOR EACH STATEMENT`. Los dos lanzan `price_observations is append-only`.

Mixins de SQLAlchemy en `infrastructure/db/models.py`: `IdMixin` (`id`), `CreatedAtMixin` (`created_at` con `server_default=now()`) y `TimestampsMixin` (`created_at` y `updated_at`). `price_observations` usa los dos primeros.

**Coordenadas:** se escriben como `WKTElement("POINT(lon lat)", srid=4326)` y se leen con `ST_Y(geometry(location))` y `ST_X(geometry(location))`, sin `shapely`. Este patrón pasa pyright estricto; `geoalchemy2.shape.to_shape` no (probado el 28 oct con SQLAlchemy 2.1.6 y GeoAlchemy2 0.20.0).

### Semilla (`seeds/projects.json`)

Tres proyectos reales, cada uno con su constructora, al menos una tipología y una observación de precio con `source = "manual"` y la URL pública de donde salió. Andrés copia los datos a mano desde el sitio de cada constructora; no se usa scraping. El archivo se valida con modelos Pydantic en `src/sobreplano/interface/cli/seed_schema.py` antes de tocar la base de datos.

### Configuración

- `DATABASE_URL`, documentada en `.env.example`. En local: `postgresql+psycopg://postgres:postgres@127.0.0.1:54322/postgres`.
- Los comandos que usan la base de datos se corren con `uv run --env-file .env ...`.

## Plan de implementación

1. **Plugin.** Auditar `supabase/agent-skills` (leer el `SKILL.md` y los scripts) y habilitar `postgres-best-practices` en `.claude/settings.json` (`extraKnownMarketplaces` y `enabledPlugins`). Confirmar el identificador exacto con `/plugin`. Commit `chore:`.
2. **Supabase local.** `supabase init`, versionar `supabase/config.toml`, crear `.env.example`. `supabase db start` levanta Postgres en el puerto 54322. Commit `chore:`.
3. **Dependencias.** Agregar las cinco dependencias de runtime. Ampliar `forbidden_modules` a `["sqlalchemy", "fastapi", "geoalchemy2", "psycopg", "alembic"]`. Registrar el marcador `integration` en `[tool.pytest.ini_options]`. Los cinco controles siguen en verde. Commit `chore:`.
4. **Dominio.** `catalog.py`, `pricing.py`, `errors.py` y `ports.py`, con tests unitarios en `tests/unit/domain/` (rango de coordenadas, áreas, precio positivo, zona horaria obligatoria). Commit `feat:`.
5. **Caso de uso.** `application/record_price_observation.py`: recibe `unit_type_id`, `price_cop`, `observed_at`, `source` y `source_url`; calcula `observed_on` en America/Bogota; si `exists_for_day` es verdadero no inserta y devuelve `RecordResult.ALREADY_RECORDED`, si no inserta y devuelve `RecordResult.RECORDED`. Tests con un repositorio en memoria en `tests/unit/application/`. Commit `feat:`.
6. **Modelos y motor.** `infrastructure/db/engine.py` (motor y `sessionmaker` desde `DATABASE_URL`) y `infrastructure/db/models.py` (mixins, cuatro tablas y restricciones). Commit `feat:`.
7. **Alembic.** `alembic.ini` y `migrations/env.py` (URL desde `DATABASE_URL`, `target_metadata` de los modelos, helpers de GeoAlchemy2 para Alembic). Migración `0001_schema_v1` con `--rev-id 0001`, revisada a mano para agregar PostGIS, RLS y los triggers. `upgrade head`, `downgrade base` y otra vez `upgrade head` funcionan. Commit `feat:`.
8. **Repositorios.** `infrastructure/db/catalog_repository.py` y `infrastructure/db/price_observation_repository.py`, que traducen entre filas y entidades. Tests de integración en `tests/integration/` con un fixture que abre una transacción por test y la revierte al final. Commit `feat:`.
9. **Reglas de la base de datos.** Tests de integración que prueban que: `UPDATE`, `DELETE` y `TRUNCATE` sobre `price_observations` fallan; una segunda observación del mismo día para la misma tipología falla; una tipología sin áreas falla; RLS está activo en las cinco tablas (`pg_class.relrowsecurity`); y un punto guardado devuelve las mismas lat y lon. Commit `test:`.
10. **Semilla.** `seeds/projects.json` con los 3 proyectos, `seed_schema.py` y `interface/cli/seed.py`. Es idempotente: salta lo que ya existe por `slug` y usa el caso de uso para las observaciones. Commit `feat:`.
11. **CI.** En `.github/workflows/ci.yml`: instalar la CLI con `supabase/setup-cli@v1`, `supabase db start`, `DATABASE_URL` como variable del job, y luego `alembic upgrade head`, `alembic check`, `test "$(uv run alembic heads | wc -l)" -eq 1` y `pytest` (ya incluye integración). Commit `chore:`.
12. **Documentación.** Constitución v1.1.0; `docs/schema.md` con un `erDiagram` de Mermaid; en `CLAUDE.md`, el estado del proyecto, los comandos de base de datos, `migrations/` como carpeta real y el enlace a `docs/schema.md`; en el README, "week 2 of 8". Commit `docs:`.

Cada paso deja el repo con los controles en verde y se puede commitear solo.

## Criterios de aceptación

Cada criterio se verifica pegando el comando y su salida en el PR (constitución, principio 6).

- [ ] `supabase db start` termina sin error y `psql "postgresql://postgres:postgres@127.0.0.1:54322/postgres" -c "select postgis_version()"` devuelve una versión después de `alembic upgrade head`.
- [ ] `uv run --env-file .env alembic upgrade head`, luego `alembic downgrade base` y otra vez `alembic upgrade head` terminan con código 0.
- [ ] `uv run --env-file .env alembic check` imprime `No new upgrade operations detected.`
- [ ] `uv run alembic heads` imprime una sola línea: `0001 (head)`.
- [ ] `uv run pytest -m "not integration"` pasa sin base de datos levantada.
- [ ] `uv run --env-file .env pytest` pasa completo, incluidos los tests de integración de los pasos 8 y 9.
- [ ] `uv run pyright` termina con 0 errores y `uv run lint-imports` reporta 2 contratos cumplidos.
- [ ] Prueba negativa: agregar temporalmente `import geoalchemy2` en `src/sobreplano/domain/catalog.py` hace fallar `uv run lint-imports`; se revierte antes del commit.
- [ ] `hasattr(SqlPriceObservationRepository, "update")` y `hasattr(SqlPriceObservationRepository, "delete")` son falsos (test unitario).
- [ ] `uv run --env-file .env python -m sobreplano.interface.cli.seed` deja 3 proyectos, al menos 3 tipologías y al menos 3 observaciones; correrlo una segunda vez no agrega filas (conteos antes y después en el PR).
- [ ] El CI corre en el PR con la base de datos de Supabase, y todos sus pasos, incluidos `alembic check` y la verificación de una sola cabeza, quedan en verde (enlace a la ejecución en el PR).
- [ ] `docs/constitution.md` dice `Versión 1.1.0`, el principio 2 ya no usa `grep` y el changelog tiene la entrada 1.1.0.
- [ ] `docs/schema.md` muestra el diagrama en GitHub con las cuatro tablas y sus relaciones.
- [ ] `git status` no muestra `.env` ni archivos de `supabase/.temp/`.

## Decisiones tomadas y descartadas

- **Sí:** el trigger append-only en la base de datos, además de la API del repositorio. La regla queda protegida aunque alguien entre por `psql`, por un script o por un error en otro repositorio.
- **Sí:** el trigger también bloquea `TRUNCATE`, porque los triggers por fila no lo ven.
- **Sí:** enmendar la constitución a v1.1.0. El `grep` de `UPDATE|DELETE` del principio 2 daría falso positivo con el propio trigger, y es más débil que probar contra la base de datos. La nueva verificación tiene dos tests: el repositorio no tiene `update` ni `delete`, y la base de datos rechaza `UPDATE`, `DELETE` y `TRUNCATE`.
- **Sí:** una observación por tipología y por día, con único (`unit_type_id`, `observed_on`). Como la tabla es append-only, un duplicado no se podría borrar; por eso se evita antes de insertar. El caso de uso lo revisa primero para que reintentar un scraper no sea un error.
- **Sí:** `observed_on` como columna explícita que calcula la aplicación en America/Bogota. Una columna generada con `AT TIME ZONE` hace lo mismo con más magia.
- **Sí:** precio en `bigint` de pesos enteros. Los precios de vivienda en Colombia no usan centavos y `bigint` evita los errores de redondeo de `float`.
- **Sí:** dos áreas opcionales (privada y construida) con un CHECK de que exista al menos una. Las constructoras publican una, la otra o las dos, y el precio por m² de la semana 4 usa la privada cuando existe.
- **Sí:** el precio se observa por tipología, no por proyecto, para poder calcular el precio por m².
- **Sí:** rango de coordenadas del Valle de Aburrá en `GeoPoint`. Detecta el error más común con coordenadas: invertir latitud y longitud.
- **Sí:** `geography(POINT, 4326)` con GeoAlchemy2 y lectura con `ST_X`/`ST_Y`. **No:** `shapely` ni `to_shape`, que dejan tipos desconocidos y rompen pyright estricto.
- **Sí:** municipio y fuente como `varchar` con CHECK (`Enum(..., native_enum=False, create_constraint=True, length=16)`; sin `create_constraint=True` SQLAlchemy no crea el CHECK). **No:** un enum nativo de Postgres, que es más difícil de cambiar en una migración.
- **Sí:** UUID generados en el dominio con `uuid4`. **No:** `gen_random_uuid()` como única fuente, porque obligaría a ir a la base de datos para tener identidad.
- **Sí:** RLS activado sin políticas en todas las tablas, incluida `alembic_version`. En Supabase, una tabla de `public` sin RLS queda expuesta por la API REST en cuanto exista el proyecto en la nube. Se deja hecho desde la primera migración.
- **Sí:** Alembic como único dueño del esquema. **No:** `supabase/migrations/`; dos herramientas de migraciones sobre la misma base de datos terminan en conflicto.
- **Sí:** SQLAlchemy síncrono con psycopg 3. Basta para la API y para los scrapers en Lambda, y es más simple de tipar. **No:** asíncrono por ahora.
- **Sí:** `DATABASE_URL` leída del entorno y `uv run --env-file .env`. **No:** `pydantic-settings` todavía; entra con la API en SPEC 03.
- **Sí:** el mismo Postgres de Supabase en local y en CI (`supabase db start`). **No:** la imagen `postgis/postgis` en CI, que no tiene el esquema `extensions` ni la configuración de Supabase.
- **Sí:** tests de integración con una transacción revertida por test. El trigger bloquea `TRUNCATE`, así que no se puede limpiar la tabla entre tests.
- **No:** tabla `scrape_runs` en este spec. Sin scrapers no se sabe qué columnas necesita; agregar la relación después es una migración pequeña.
- **No:** proyecto de Supabase en la nube en este spec. El plan gratuito se pausa tras 7 días sin actividad, y nada lo usa hasta la semana 3.
- **Sí:** semilla en `seeds/` y no en `data/`, que está ignorada por `.gitignore`.

## Riesgos identificados

| Riesgo | Mitigación |
| --- | --- |
| `supabase db start` descarga una imagen grande y alarga el CI | Se mide en el primer PR. Si pasa de 3 minutos, se cachea la imagen o se usa la imagen `supabase/postgres` como servicio del job |
| El tipo `geography` no se resuelve porque `extensions` no está en el `search_path` de la conexión | Test de integración del punto (paso 9). Si falla, se agrega `options=-csearch_path=public,extensions` a la URL |
| `alembic check` detecta diferencias falsas por el índice GIST o por objetos de PostGIS | `migrations/env.py` usa los helpers de GeoAlchemy2 para Alembic y un `include_object` que solo compara el esquema `public` |
| Las funciones de PostGIS no tienen tipos en SQLAlchemy | `type_=Float()` en `ST_X`/`ST_Y` y `func.geometry(...)` en vez de `cast(..., Geometry)`, ya probado con pyright estricto |
| Los datos de la semilla cambian en el sitio de la constructora | La observación guarda `observed_at` y `source_url`; el histórico real arranca con los scrapers |
| `jq` o la CLI de Supabase no están instalados en la máquina | `CLAUDE.md` lista las dos herramientas con su comando de instalación (`brew install supabase/tap/supabase`) |

## Lo que **no** entra en este spec

- Proyecto de Supabase en la nube.
- Tabla `scrape_runs`.
- Consultas de último precio, endpoints y FastAPI.
- Usuarios, autenticación y alertas.
- pgvector y embeddings.
- VIS/VIP, etapa del proyecto y zonas como polígonos.
- SQLAlchemy asíncrono, `pydantic-settings` y MCP de Supabase.

Cada uno, si llega, va en su propio spec.
