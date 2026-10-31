# SPEC 04 — Primer scraper: Londoño Gómez en local

> **Estado:** implementado
> **Depende de:** SPEC 02, SPEC 03
> **Fecha:** 2026-10-30 (proveedor de extracción cambiado a OpenAI el mismo día)
> **Objetivo:** Correr en local `python -m sobreplano.interface.cli.scrape londono-gomez`, que visita una vez las fichas públicas de vivienda de Londoño Gómez en el Valle de Aburrá, guarda el HTML crudo, extrae las tipologías con un LLM (GPT-6 Luna por defecto) y registra un precio por tipología y por día.

## Por qué existe este spec

Hoy los precios entran solo por la semilla manual. Sin un scraper no hay histórico, y el histórico es el diferenciador de Sobreplano. Este spec construye el scraper completo en local. SPEC 05 lo lleva a AWS para que corra solo cada día.

Londoño Gómez se eligió el 30 oct porque publica precio "desde" por tipología con su área, tiene proyectos en cinco municipios del Valle y su `robots.txt` no bloquea las fichas.

Lo que se sabe del sitio (lectura del 30 oct, sin descargar el HTML crudo):

- Fichas con URL canónica `/proyectos-vivienda/antioquia/{municipio}/{slug}`, por ejemplo `/proyectos-vivienda/antioquia/bello/primavela`.
- Cada tipología es un bloque con nombre ("TIPO B", "Tipo 1"), precio ("Desde $506.100.000 *") y área ("Área total: 55.58 m2 *"). Algunas fichas agregan "Área privada", alcobas ("2 o 3 alcobas") y baños; otras no. Hay bloques sin precio, como "PLANTA TÍPICA".
- Las coordenadas están en el enlace de Google Maps: `https://www.google.com/maps/dir//6.3296009,-75.5595542/@...`, en orden latitud, longitud.
- Hay proyectos "Outlet" (inventario con descuento) que repiten un proyecto normal.

Lo que confirmó la exploración del paso 1 (30 oct, HTML crudo descargado con `httpx`):

- Las tipologías vienen en el HTML inicial (bloques `.detail-apartment` con `h4` y `span.price-apartament-types`); no hace falta Playwright. El texto limpio de una ficha mide entre 3.000 y 5.000 caracteres.
- `www.londonogomez.com` redirige con 301 a `londonogomez.com`. Su `robots.txt` solo bloquea `/core/`, `/profiles/`, `/admin/`, `/search/`, `/user/…` y similares; `/proyectos-vivienda` y las fichas están permitidas.
- El listado es `https://londonogomez.com/proyectos-vivienda`: 62 tarjetas en `.view-busqueda-proyectos .views-row`, sin paginación. Mezcla vivienda, lotes, oficinas y hotel, y municipios fuera del Valle (Rionegro, La Ceja, El Retiro, Bogotá, Barranquilla).
- Cada tarjeta enlaza a `/node/{N}` (`a[href^="/node/"]`), no a la URL canónica. Pedir `/node/{N}` responde 301 a la canónica, y la ficha trae `<link rel="canonical">`.
- La tarjeta muestra el título (`.views-field-title`), el tipo (`.views-field-field-tipo-de-proyecto`: `Vivienda`, `Lotes`, `Oficinas`, `Hotel`) y el municipio (`.views-field-nothing`, por ejemplo `Medellín`, `La Estrella`). Las 3 tarjetas sin municipio tampoco tienen tipo (entradas de prueba como "prueba" o "Verde M").
- Con los filtros de tarjeta de abajo quedan 25 fichas en 5 municipios (Medellín, Bello, Envigado, Sabaneta, La Estrella). Varias no publican precio.

Estado actual del repo (`main` en `01785e3`):

- `src/sobreplano/application/record_price_observation.py` registra una observación por tipología y día, pero un `IntegrityError` por inserción simultánea sube como error.
- `src/sobreplano/domain/catalog.py`: `UnitType.bedrooms` y `bathrooms` son `int` obligatorios, y la migración `0001` los crea `NOT NULL`. Primavela no publica alcobas.
- `src/sobreplano/domain/ports.py:11-19`: `CatalogRepository` tiene `get_project_by_slug` y `list_unit_types`, suficientes para crear sin duplicar.
- `src/sobreplano/infrastructure/db/geo.py` es el único lugar que arma `POINT(lon lat)`.
- `.gitignore` ya ignora `data/`.
- No existen `openai`, `httpx` como dependencia directa ni un parser de HTML.
- El documento del proyecto "Modelo de extracción para el scraper" (30 oct) dejó el formato `proveedor:modelo` y un adaptador compatible con OpenAI para el SPEC 10. Este spec lo adelanta, porque no hay saldo en la API de Anthropic y sí en la de OpenAI.

## Alcance

**Dentro:**

- Migración `0002`: tablas `scrape_runs`, `scraped_pages` y `page_extractions`; `bedrooms` y `bathrooms` pasan a opcionales.
- Puertos en el dominio: `PageFetcher`, `RawPageStore`, `ProjectPageExtractor`, `ScrapeRunRepository` y `DeveloperSite`.
- Caso de uso `ScrapeDeveloper` en `application/`.
- Fetcher con `httpx`: user-agent del proyecto, `robots.txt`, 2 s entre peticiones y una visita por URL por corrida.
- Almacén de HTML crudo en disco (`data/raw/`), detrás del puerto; S3 llega en SPEC 05.
- Parser determinista (BeautifulSoup) para descubrir fichas, la URL canónica y las coordenadas.
- Extracción con un LLM del nombre, el sector y las tipologías, con salida estructurada estricta (Pydantic), guardando modelo y tokens (constitución, principio 5).
- Un solo adaptador, `OpenAICompatibleExtractor`, sobre Chat Completions. Sirve para OpenAI hoy y para Qwen mañana, porque Alibaba expone una API compatible con OpenAI.
- `EXTRACTION_MODEL` con formato `proveedor:modelo`, por defecto `openai:gpt-6-luna`; una fábrica elige el adaptador.
- Reutilizar la extracción si el hash del HTML no cambió: no se vuelve a llamar al modelo.
- Validación de rangos antes de guardar, como primera defensa contra contenido raro o inyectado.
- `RecordPriceObservation` traduce el `IntegrityError` de la restricción única a `ALREADY_RECORDED`.
- CLI `interface/cli/scrape.py` con `--limit` y `--dry-run`.
- Tests con HTML sintético escrito a mano y extractor falso; un test opcional contra la API real.

**Fuera de alcance (para specs futuros):**

- S3, Lambda, SQS, EventBridge, Terraform y Supabase en la nube: SPEC 05.
- Playwright: entra cuando un sitio no traiga los datos en el HTML inicial.
- Otras constructoras, skill `/add-scraper` y deduplicar alianzas entre constructoras: SPEC 06.
- Proyectos "Outlet": se saltan; su precio es de inventario con descuento, no de lista.
- Estado del proyecto (nuevo, en construcción, entrega) como columna.
- Marcar proyectos que desaparecen del sitio.
- Actualizar áreas o nombres de tipologías que cambian después de creadas.
- Golden set y evals de la extracción: SPEC 10.

## Modelo de datos

### Migración `0002_scraping` (escrita y revisada a mano, según "Migration rules" de `CLAUDE.md`)

| Tabla | Columnas | Restricciones |
| --- | --- | --- |
| `scrape_runs` | `id`, `developer_id` → `developers`, `run_on date`, `started_at`, `finished_at null`, `status varchar(16)` (`running`, `succeeded`, `failed`), `pages_fetched`, `pages_failed`, `observations_recorded` (int, por defecto 0), `error text null`, `created_at`, `updated_at` | CHECK de `status` |
| `scraped_pages` | `id`, `scrape_run_id` → `scrape_runs`, `url text` (URL canónica, nunca `/node/N`), `http_status smallint`, `content_sha256 char(64)`, `storage_key text`, `fetched_at`, `created_at` | único (`scrape_run_id`, `url`) |
| `page_extractions` | `id`, `content_sha256 char(64)`, `model text`, `input_tokens int`, `output_tokens int`, `payload jsonb`, `created_at` | único (`content_sha256`, `model`) |

- `unit_types.bedrooms` y `unit_types.bathrooms` pasan a `NULL` con `op.alter_column`. Cuando la ficha da un rango ("2 o 3 alcobas"), se guarda el mínimo.
- RLS activado en las tres tablas nuevas, igual que en `0001`.
- `page_extractions` guarda el resultado validado; si el mismo HTML vuelve a aparecer, se reutiliza sin costo.

### Salida de la extracción (`infrastructure/scraping/extraction_schema.py`, Pydantic)

```python
class ExtractedUnitType(BaseModel):
    name: str
    price_cop: int | None  # "Desde $506.100.000" -> 506100000; None si no hay precio
    total_area_m2: float | None  # float, no Decimal: portable entre modos estrictos
    private_area_m2: float | None
    bedrooms: int | None  # mínimo si es un rango
    bathrooms: int | None


class ExtractedProject(BaseModel):
    name: str
    neighborhood: str | None  # sector o barrio, por ejemplo "Pan de Azúcar"
    unit_types: list[ExtractedUnitType]
```

Todos los campos son obligatorios y anulables, sin valores por defecto, como exige el modo estricto de OpenAI. Las áreas pasan a `Decimal` al convertirse en entidades del dominio.

El municipio, el slug y las coordenadas no los extrae el modelo: salen de la URL canónica y del enlace de Google Maps con el parser determinista. Así el orden latitud/longitud nunca depende del modelo.

### Reglas de validación (`domain/scraping.py`)

Una tipología se guarda solo si:

- tiene precio entre 50.000.000 y 20.000.000.000 COP;
- tiene al menos un área entre 15 y 1.000 m²;
- `total_area_m2` se guarda como `built_area_m2` y `private_area_m2` como `private_area_m2`.

Además:

- Un área fuera de rango se descarta (queda en `None`) y se registra en el log; la tipología se guarda con la otra si esa sí está en rango.
- Alcobas y baños: el modelo devuelve el mínimo cuando hay un rango. El dominio solo acepta valores entre 0 y 10; fuera de eso quedan en `None`, sin descartar la tipología.

Las tipologías que no cumplen se cuentan y se registran en el log con la URL, pero no frenan la corrida.

### Puertos (`domain/ports.py`)

```python
class PageFetcher(Protocol):
    def fetch(self, url: str) -> FetchedPage: ...  # url, status, html, fetched_at


class RawPageStore(Protocol):
    def save(self, developer_slug: str, page: FetchedPage) -> str: ...  # storage_key


class ProjectPageExtractor(Protocol):
    model: str  # "proveedor:modelo"; el caso de uso lo necesita para buscar la extracción guardada

    def extract(self, page_text: str) -> ExtractionResult: ...  # proyecto, modelo y tokens


class ScrapeRunRepository(Protocol):
    def start(self, developer_id: UUID, run_on: date) -> ScrapeRun: ...
    def record_page(self, run_id: UUID, page: ScrapedPage) -> None: ...
    def find_extraction(self, content_sha256: str, model: str) -> ExtractionResult | None: ...
    def save_extraction(self, content_sha256: str, result: ExtractionResult) -> None: ...
    def finish(self, run: ScrapeRun) -> None: ...


class DeveloperSite(Protocol):
    slug: str  # "londono-gomez"
    name: str
    website_url: str
    listing_url: str

    def project_urls(self, listing_html: str) -> list[str]: ...  # ya filtradas por la tarjeta
    def parse_project(
        self, page: FetchedPage
    ) -> ParsedProjectPage | None: ...  # None: fuera de alcance
```

`DeveloperSite` existe porque `application/` no puede importar el parser (usa `bs4`, vive en `infrastructure/`). Cada constructora es una implementación; la de este spec es `LondonoGomezSite`. `ParsedProjectPage` lleva `canonical_url`, `municipality`, `slug`, `location` y `text` (el texto limpio que va al extractor). Si la ficha está dentro del alcance pero no trae canonical o enlace de Google Maps válido, `parse_project` lanza `PageParseError` y la ficha cuenta como error.

Los tipos `FetchedPage`, `ScrapeRun`, `ScrapedPage`, `ExtractionResult` y `ParsedProjectPage` son dataclasses del dominio. `ExtractionResult` lleva `model`, `input_tokens`, `output_tokens` y el proyecto extraído en forma de dataclasses, no de Pydantic.

### Configuración

`Settings` suma:

- `extraction_model: str = "openai:gpt-6-luna"`. La fábrica falla al arrancar si el proveedor no tiene configuración.
- `openai_api_key`, opcional: sin ella no se puede extraer, pero sí reutilizar extracciones guardadas.
- Para Qwen, más adelante y sin código nuevo: `qwen_api_key` y `qwen_base_url`.

Cada proveedor es una entrada en una tabla de configuración (`infrastructure/scraping/providers.py`): `base_url`, nombre de la variable de la clave y parámetros extra. Para OpenAI, `reasoning_effort="none"`. Qwen se agrega cuando se pruebe, con su parámetro para apagar el razonamiento verificado en su documentación. `.env.example` documenta el formato `proveedor:modelo`. `ExtractionResult.model` guarda el string completo, que también forma parte de la llave de reutilización: cambiar de modelo vuelve a extraer sin mezclar resultados.

## Plan de implementación

1. **Exploración (sin código del proyecto).** Con `httpx` y el user-agent del proyecto, bajar una vez el listado y dos fichas (Primavela y Réflex Living) a `data/raw/explore/`. Confirmar que las tipologías están en el HTML inicial, anotar los selectores del listado, la URL canónica y el enlace de Google Maps, y medir el tamaño del texto limpio. Si las tipologías no están en el HTML, parar y actualizar el spec para usar Playwright.
2. **Dependencias y migración.** `uv add openai httpx beautifulsoup4`. Migración `0002` con las tres tablas, RLS y las columnas opcionales; modelos SQLAlchemy al día. `alembic check` limpio. Commit `feat:`.
3. **Dominio.** Dataclasses de scraping, reglas de validación y puertos, con tests unitarios de los rangos y del mínimo de alcobas. Commit `feat:`.
4. **`IntegrityError`.** `RecordPriceObservation` atrapa la violación de la restricción única y devuelve `ALREADY_RECORDED`. Para no meter SQLAlchemy en `application/`, el repositorio traduce el error a `DuplicateObservationError` del dominio. Test de integración con dos inserciones del mismo día. Commit `fix:`.
5. **Parser determinista.** Puerto `DeveloperSite`, `ParsedProjectPage` y `PageParseError` en el dominio, y `LondonoGomezSite` en `infrastructure/scraping/londono_gomez.py`:
   - Tarjetas del listado → enlaces `/node/{N}`, filtrados **antes** de pedir la ficha. Se descarta la tarjeta si el título contiene "outlet" o "prueba" (sin importar mayúsculas), si el tipo no es `Vivienda` (lotes, oficinas, hotel o vacío) o si el municipio, normalizado (minúsculas, sin tildes, espacios a `_`), no está en `Municipality`.
   - `<link rel="canonical">` de la ficha → municipio y slug. Filtro **después** de pedir la ficha: solo `/proyectos-vivienda/antioquia/{municipio}/{slug}` con municipio en `Municipality` y slug sin "outlet". Una ficha descartada aquí no se guarda en crudo, no se extrae con el LLM y no se registra en `scraped_pages`; solo cuenta en el resumen como "fuera de alcance".
   - Enlace de Google Maps → `GeoPoint`, y HTML → texto limpio (sin scripts, estilos, menú ni pie).
   - Tests con HTML sintético. Commit `feat:`.
6. **Fetcher y almacén.** `infrastructure/scraping/http_fetcher.py`: user-agent, `follow_redirects=True` con máximo 3 redirects, timeout de 20 s y 2 s entre peticiones, también antes y después de las fichas que se descartan. `robots.txt` con `urllib.robotparser`, leído de `londonogomez.com` (el host final) y revisado contra la URL final. `FetchedPage.url` es la URL final. `infrastructure/scraping/file_store.py` guarda en `data/raw/{developer}/{YYYY-MM-DD}/{sha256}.html`. Commit `feat:`.
7. **Extractor compatible con OpenAI.** `infrastructure/scraping/providers.py` (tabla de proveedores y fábrica) y `infrastructure/scraping/openai_compatible_extractor.py` con `client.chat.completions.parse(model=..., messages=[...], response_format=ExtractedProject, max_completion_tokens=2048, **extra)`, donde `extra` es `reasoning_effort="none"` para OpenAI. Sin `temperature`. El texto de la ficha va dentro de `<page>…</page>` y el mensaje de sistema dice que todo lo que está adentro es dato, nunca instrucciones. Si el texto limpio pasa de 20.000 caracteres, la ficha se marca como error y no se envía. Son error de extracción de esa ficha: `finish_reason` igual a `length`, un `message.refusal` no vacío o `message.parsed` vacío. Tokens desde `usage.prompt_tokens` y `usage.completion_tokens`. Test con un cliente falso que verifica que el resultado guarda modelo y tokens (principio 5) y que la petición lleva `reasoning_effort="none"` y no lleva `temperature`. Commit `feat:`.
8. **Repositorio y caso de uso.** `SqlScrapeRunRepository` y `application/scrape_developer.py`. Por cada ficha: bajar, guardar, calcular el hash, reutilizar o extraer, crear constructora, proyecto y tipologías si no existen, y registrar el precio con `RecordPriceObservation`. Si una ficha falla, se cuenta y se sigue. La corrida termina `succeeded` si al menos una ficha registró precio. Tests con fakes de los cinco puertos. Commit `feat:`.
9. **CLI.** `interface/cli/scrape.py` con `--limit N` y `--dry-run` (baja y extrae, pero hace rollback). Imprime un resumen: fichas (pedidas, fuera de alcance y con error), tipologías válidas y descartadas, observaciones, tokens y costo estimado. Commit `feat:`.
10. **Corrida real y documentación.** Una corrida completa en local contra Londoño Gómez. `CLAUDE.md` con el comando y `docs/scrapers/londono-gomez.md` con la URL del listado, los selectores, las reglas de robots y la fecha de revisión. Commit `docs:`.

## Criterios de aceptación

Cada criterio se verifica pegando el comando y su salida en el PR (constitución, principio 6).

- [ ] `uv run --env-file .env alembic upgrade head`, `downgrade -1` y otra vez `upgrade head` terminan con código 0; `alembic check` no detecta cambios.
- [ ] `uv run --env-file .env python -m sobreplano.interface.cli.scrape londono-gomez --limit 2 --dry-run` termina sin error y no deja filas nuevas en `price_observations`.
- [ ] La corrida completa registra al menos 10 proyectos en al menos 3 municipios y al menos 30 observaciones (consulta de conteos en el PR).
- [ ] Una segunda corrida el mismo día no agrega observaciones (`ALREADY_RECORDED`) y no llama al modelo: el resumen muestra 0 tokens porque todos los hashes ya estaban.
- [ ] `select count(*) from page_extractions where model = '' or input_tokens = 0` devuelve 0.
- [ ] `curl -s "localhost:8000/projects?municipality=sabaneta" | jq .total` devuelve al menos 1 con la API de SPEC 03.
- [ ] Ningún proyecto con "outlet" en el slug: `select count(*) from projects where slug ilike '%outlet%'` devuelve 0.
- [ ] Las coordenadas de Primavela guardadas son 6.3296 y -75.5596 (redondeadas a 4 decimales).
- [ ] `git status` no muestra nada de `data/raw/`.
- [ ] `uv run pytest -m "not integration"` pasa sin base de datos ni API key; `uv run --env-file .env pytest` pasa completo.
- [ ] `uv run pyright` termina con 0 errores y `uv run lint-imports` reporta 2 contratos cumplidos (`openai`, `httpx` y `bs4` agregados a `forbidden_modules`).
- [ ] El costo de la corrida completa, calculado con los tokens guardados, es menor a 0,10 USD.
- [ ] El CI del PR queda en verde.

## Decisiones tomadas y descartadas

- **Sí:** `httpx` en vez de Playwright, siempre que el paso 1 confirme que los datos están en el HTML inicial. Es más rápido, más barato y deja la imagen de Lambda de SPEC 05 sin navegador. **No:** Playwright "por si acaso"; entra con el primer sitio que lo necesite.
- **Sí:** extracción con un LLM para nombre, sector y tipologías. Las fichas varían (con o sin área privada, alcobas como rango, bloques sin precio) y los selectores fijos se romperían con cada variación.
- **Sí:** municipio, slug y coordenadas con parser determinista. Son datos estructurados en la URL y en el enlace del mapa; pedírselos al modelo solo agrega riesgo de invertir latitud y longitud.
- **Sí:** `openai:gpt-6-luna` por defecto. Cuesta lo mismo que Claude Haiku 5.5 (0,10 / 0,50 USD por millón de tokens), tiene salida estructurada estricta y permite apagar el razonamiento. Se cambia porque la cuenta de Anthropic no tiene saldo y la de OpenAI sí.
- **Sí:** razonamiento apagado (`reasoning_effort="none"`). Viene en `medium` por defecto y esos tokens se cobran como salida; extraer no necesita razonar.
- **Sí:** un adaptador sobre Chat Completions y no sobre la Responses API. OpenAI recomienda Responses, pero Chat Completions es el formato que comparten Qwen, Groq, OpenRouter y Ollama, así que un solo adaptador sirve para todos cambiando `base_url`.
- **Sí:** Qwen3.7-Flash como siguiente candidato (unas 3,5 veces más barato). Entra como una fila de configuración, sin código nuevo, después de comprobar que su región soporta `json_schema` estricto y cómo apagar su razonamiento. **No:** el adaptador de Anthropic en este spec; vuelve cuando haya saldo y el golden set del SPEC 10 compare modelos.
- **Sí:** `chat.completions.parse` con un modelo Pydantic. Revisar `refusal` y `finish_reason`, porque una negativa o una respuesta cortada pueden llegar con estado 200.
- **Sí:** reutilizar la extracción por hash del HTML y modelo. La mayoría de días el HTML no cambia; así el costo diario tiende a cero.
- **Sí:** guardar modelo y tokens en `page_extractions`. Cumple el principio 5 y da el costo por corrida para el case study. **No:** una tabla `llm_usage` general todavía; llega con el asesor en SPEC 08.
- **Sí:** rangos de precio y área validados antes de guardar. Una tipología con un precio absurdo, por error del modelo o por texto inyectado en la página, no entra al histórico, que además no se puede corregir porque es append-only.
- **Sí:** "una visita por sitio al día" significa una pasada por día: cada URL se pide una sola vez por corrida, con 2 s entre peticiones.
- **Sí:** HTML crudo en disco detrás de `RawPageStore`. SPEC 05 cambia solo la implementación a S3.
- **Sí:** `bedrooms` y `bathrooms` opcionales, con el mínimo cuando hay rango. **No:** inventar un valor cuando la ficha no lo publica.
- **Sí:** el repositorio traduce `IntegrityError` a un error del dominio. `application/` no puede importar SQLAlchemy.
- **Sí:** descubrir por `/node/N` y resolver el municipio con la canonical; una sola petición por proyecto. Lo que se descarta después de pedirlo no se guarda ni se extrae.
- **Sí:** filtrar primero con los datos de la tarjeta (título, tipo y municipio) para no pedir fichas de lotes, oficinas o municipios fuera del Valle.
- **Sí:** un quinto puerto, `DeveloperSite`, para el parser de cada constructora. **No:** meter el parser dentro del extractor (mezcla lo determinista con el LLM) ni dejar el descubrimiento en la CLI.
- **Sí:** saltar los proyectos "Outlet". Su precio es de inventario con descuento y duplicaría proyectos que ya existen.
- **Sí:** tests con HTML sintético escrito a mano. La constitución prohíbe versionar HTML scrapeado.
- **No:** crear o actualizar tipologías cuando cambia su área. En v1 se crean una vez; los cambios se registran en el log.

## Riesgos identificados

| Riesgo | Mitigación |
| --- | --- |
| Las tipologías se cargan con JavaScript | El paso 1 lo detecta antes de escribir código; si pasa, se actualiza el spec a Playwright |
| El sitio cambia de estructura y el parser no encuentra fichas | La corrida termina `failed` si ninguna ficha registra precio, con el error guardado en `scrape_runs.error` |
| Cambiar de modelo (GPT-6 Luna a Qwen) baja la calidad sin que se note | El string `proveedor:modelo` se guarda en cada extracción y es parte de la llave de reutilización; el golden set del SPEC 10 compara modelos antes de cambiar el de producción |
| El modelo inventa o lee mal un precio | Validación de rangos; el golden set de SPEC 10 mide la precisión |
| Texto en la página que intenta dar instrucciones al modelo | Prompt de sistema que trata la página como dato, salida restringida por esquema y validación de rangos. Los guardrails completos llegan en SPEC 11 |
| El nombre de una tipología cambia de un día a otro ("TIPO B" a "Tipo B") | Se compara en minúsculas y sin espacios repetidos al buscar la tipología existente |
| El precio "desde" de la ficha usa dólares | Se ignora el bloque "Precio en USD"; solo se aceptan precios en pesos dentro del rango |

## Lo que **no** entra en este spec

- AWS, Terraform, Supabase en la nube y ejecución programada.
- Playwright.
- Otras constructoras, `/add-scraper` y deduplicar alianzas.
- Proyectos "Outlet".
- Estado del proyecto y proyectos que desaparecen.
- Golden set y evals.

Cada uno, si llega, va en su propio spec.
