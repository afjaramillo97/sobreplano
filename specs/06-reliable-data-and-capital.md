# SPEC 06 — Datos confiables y segunda constructora: Constructora Capital

> **Estado:** aprobado
> **Depende de:** SPEC 04, SPEC 05
> **Fecha:** 2026-11-02
> **Objetivo:** Que el scraper diario no pierda precios, no vuelva a extraer páginas que no cambiaron y cubra también a Constructora Capital, con un horario propio por constructora en AWS.

## Por qué existe este spec

La revisión del SPEC 05 encontró tres fallas en los datos de la primera corrida en AWS (1 nov). Antes de que el asesor use esos datos, hay que corregirlas:

1. **0 extracciones reutilizadas.** El hash se calcula sobre el HTML crudo, y el HTML cambia todos los días. Confirmado el 2 nov en la base en la nube: las 21 fichas tienen 4 hashes distintos en 4 días de descarga (`count(distinct content_sha256)` por URL en `scraped_pages`), aunque sus precios no cambiaron. Así la reutilización del SPEC 04 nunca ocurre y cada día se vuelve a pagar la extracción completa.
2. **Una tipología contada dos veces.** Cada corrida reporta `1 already recorded today`. Confirmado el 2 nov en `page_extractions.payload`: en Verdeventura (Bello) el modelo devuelve dos veces "Tipo A" con el mismo precio (260.000.000) y la misma área (52 m²). Es la misma tipología leída dos veces; no se pierde ningún precio, pero los contadores mienten y una tipología "válida" de más infla el reporte.
3. **Ezzenti falla en cada corrida** porque no tiene enlace de Google Maps.

Además, Andrés pidió cubrir al menos dos constructoras. Constructora Capital ya está en la semilla (3 proyectos de Ciudad Peldar, Envigado, cargados a mano el 28 oct) y publica precio por tipología con área privada y construida.

Estado actual del repo (`main` en `90da75b`):

- `src/sobreplano/application/scrape_developer.py:189` calcula `content_sha256(page.html)` y lo usa para el archivo crudo, para `scraped_pages` y como llave de reutilización en `_extraction` (`:207-218`).
- `src/sobreplano/domain/scraping.py:179-181`: `normalize_unit_type_name` solo pasa a minúsculas y une espacios.
- `src/sobreplano/application/scrape_developer.py:287-324`: `_unit_type` busca la tipología solo por nombre normalizado; si dos tipologías extraídas comparten nombre, la segunda reutiliza la fila de la primera.
- `migrations/versions/0001_schema_v1.py:148`: único (`project_id`, `name`) en `unit_types`.
- `migrations/versions/0002_scraping.py:72,94,108`: `content_sha256` en `scraped_pages` y `page_extractions`, con único (`content_sha256`, `model`).
- `src/sobreplano/infrastructure/scraping/londono_gomez.py:146-156`: `_location` solo lee enlaces `google.../maps/dir//lat,lon`.
- `src/sobreplano/domain/ports.py:78-95`: puerto `DeveloperSite` (slug, nombre, sitio, listado, `project_urls`, `parse_project`). `interface/composition.py:28` registra los sitios en `SITES`.
- `seeds/projects.json`: los 3 proyectos de Capital tienen slugs `axis-ciudad-peldar`, `murano-ciudad-peldar` y `acento-ciudad-peldar`, con `source_url` igual a la URL de su ficha (por ejemplo `https://www.constructoracapital.com/proyecto/1/medellin-y-alrededores/envigado/262/axis`). La constructora tiene slug `constructora-capital`.
- `infra/schedule.tf:48`: un solo schedule con `developer = "londono-gomez"` fijo.
- `infra/lambda.tf:65`: sin concurrencia reservada porque el límite de la cuenta era 5. El 2 nov AWS subió el límite de concurrencia de la cuenta a 40 en `us-east-1`.

Sitio de Capital, revisado en Chrome el 1 nov descargando el HTML sin ejecutar JavaScript (detalle en la bitácora):

- El listado, los precios, las áreas, las plantas y las coordenadas vienen en el HTML del servidor: basta `httpx`.
- `robots.txt`: `User-agent: *` sin `Disallow`.
- Listado: `/proyectos/1/medellin-y-alrededores`, 34 enlaces con el patrón `proyecto/1/medellin-y-alrededores/{zona}/{id}/{slug}`.
- La zona no siempre es el municipio: a veces es un barrio (`ciudad-del-rio`, `santa-ana`, `niquia`, `camino-verde`, `tierra-firme`).
- El listado incluye Rionegro (Monte Rosa, Valle Rosa, Bosque Rosa) y proyectos que no son vivienda en venta (Urbanity Office, Urbanity Renta Selecta).
- Precios con coma de miles (`$822,200,000`). Aparecen también rangos que no son precios de vivienda (`$ 2.400.001 – $ 4.800.000`), precios de referencia en dólares y textos de VIS en SMMLV.
- En las plantas, casi siempre solo la tipología más barata lleva precio; las demás dicen "Consultar precios y disponibilidad con Sala de Ventas".
- Las tipologías se llaman "Planta Apartamento 69.13 m2": el nombre ya incluye el área. Algunas áreas privadas vienen sin unidad (`ÁREA PRIVADA: 64.32`).
- Coordenadas en el HTML como `6.1719777,-75.5941694` y en un enlace de Waze.
- La ficha tiene una sección de avances de obra que cambia con el tiempo.

## Alcance

**Dentro:**

- Diagnóstico de las dos primeras fallas: hecho el 2 nov con consultas a la base en la nube (ver "Por qué existe este spec"). Queda por ver en el paso 1 qué parte del HTML cambia, para confirmar que el texto limpio no la incluye.
- La llave de reutilización pasa a ser el hash del **texto limpio** que se envía al modelo. El hash del HTML se mantiene para el nombre del archivo crudo.
- Migración `0004`: columna `text_sha256` en `scraped_pages`; `page_extractions.content_sha256` pasa a llamarse `text_sha256`.
- Proyectos sin ubicación (decidido el 2 nov): si la ficha no publica coordenadas y no hay entrada manual, el proyecto se guarda sin ubicación en vez de fallar; cuando la constructora publique el mapa, el scraper la detecta y la guarda. Migración `0005`: `projects.location` admite NULL.
- Tipologías con el mismo nombre dentro de una página: duplicados exactos se cuentan una vez; tipologías distintas con el mismo nombre se diferencian por área.
- Coordenadas con respaldo: enlace de Google Maps, luego enlace de Waze, luego una tabla de ubicaciones manuales en código (`infrastructure/scraping/manual_locations.py`).
- Scraper `ConstructoraCapitalSite` con `httpx`: tabla de zona a municipio, filtros de Rionegro y de proyectos que no son vivienda, coordenadas con parser determinista y la sección de avances de obra fuera del texto limpio.
- Reutilizar los 3 proyectos de la semilla por su `source_url` y sus tipologías por área, porque en la semilla se llaman "Tipo 04" y en el sitio "Planta Apartamento 60.01 m2".
- Un schedule por constructora con `for_each` en Terraform, escalonados 15 minutos.
- Concurrencia reservada de 2 en la Lambda, como tope de costo.

**Fuera de alcance (para specs futuros):**

- SQS, `/add-scraper` y más constructoras.
- Cobertura fuera del Valle de Aburrá (Antioquia y el resto del país, decidido el 2 nov). A futuro se traen todos los proyectos de cada constructora; requiere migrar el modelo de ubicación (hoy `projects.municipality` solo admite los 10 municipios del valle) y quitar los filtros de municipio de las dos constructoras. Costo estimado para todo el país: ~1,25 USD/mes de LLM sin reutilización, ~0,07 con reutilización.
- Deduplicar alianzas entre constructoras (MAZZI, Ventto del Río, River Park).
- Precio "desde" por proyecto (Conaltura, Coninsa).
- Volver a extraer el histórico ya guardado.
- Playwright: Capital no lo necesita.
- API de lectura: SPEC 07.

## Modelo de datos

### Migración `0004_text_hash` (escrita y revisada a mano)

- `scraped_pages`: nueva columna `text_sha256 char(64) null`. Las filas viejas quedan en `NULL`; las nuevas siempre la llenan.
- `page_extractions`: `op.alter_column("page_extractions", "content_sha256", new_column_name="text_sha256")` y el único se renombra a `uq_page_extractions_text_sha256_model`. Es un renombre, no borrar y crear: Alembic no lo detecta solo ("Migration rules" de `CLAUDE.md`).
- Las extracciones viejas quedan con el hash del HTML en una columna que ahora significa "hash del texto": nunca van a coincidir, así que la primera corrida después del cambio vuelve a extraer todo una vez (unos 0,005 USD por constructora). No se recalculan.

### Migración `0005_optional_location` (escrita y revisada a mano)

- `projects.location` pasa a `NULL`: `op.alter_column("projects", "location", nullable=True)`. El índice GIST no cambia.
- `downgrade` vuelve a `NOT NULL` y falla si hay proyectos sin ubicación, igual que `0003` con los `skipped`.

### Llaves

```python
def text_sha256(text: str) -> str: ...  # hash del texto limpio: llave de reutilización
def content_sha256(html: str) -> str: ...  # hash del HTML: nombre del archivo crudo
```

`ScrapeDeveloper._extraction` busca y guarda por (`text_sha256`, modelo). El texto limpio ya es lo único que ve el modelo, así que dos páginas con el mismo texto dan la misma extracción.

### Tipologías dentro de una página (`domain/scraping.py`)

`dedupe_unit_types(valid: list[ValidUnitType]) -> list[ValidUnitType]`, aplicada antes de registrar precios:

- Mismo nombre normalizado, mismas áreas y mismo precio: es la misma tipología leída dos veces (por ejemplo, en el resumen y en la tarjeta). Se queda una. **Es el caso observado** (Verdeventura, "Tipo A"). Los otros dos casos no se han visto; se cubren porque Capital y las constructoras siguientes pueden traerlos.
- Mismo nombre normalizado y áreas distintas: son tipologías distintas. A cada una se le agrega el área al nombre: `Tipo A · 55.58 m²`. El nombre guardado cumple el único (`project_id`, `name`) sin cambiar el esquema.
- Mismo nombre y mismas áreas pero precios distintos: se queda el menor, porque el sitio publica precios "desde", y se registra en el log.

`normalize_unit_type_name` suma `unicodedata.normalize("NFKC", ...)` y `casefold()`, para que "TIPO B", "Tipo B" y "Tipo B " sean la misma llave.

### Ubicación con respaldo (`infrastructure/scraping/geo_links.py`)

```python
def location_from_links(soup: BeautifulSoup) -> GeoPoint | None: ...
```

1. `google.../maps/dir//{lat},{lon}`, como hoy.
2. Waze: `waze.com/...?...to=ll.{lat}%2C{lon}`, que Londoño Gómez publica junto al de Google.
3. `infrastructure/scraping/manual_locations.py`: `MANUAL_LOCATIONS: dict[str, GeoPoint]` por slug del proyecto (por ejemplo `"ezzenti": GeoPoint(lat=..., lon=...)`), cargada a mano por Andrés desde el mapa público del proyecto, con un comentario por entrada con la URL de la fuente y la fecha de revisión.

Si ninguno da coordenadas, la ficha **no falla**: el proyecto se guarda sin ubicación (`Project.location: GeoPoint | None`) y el log lo registra con aviso. No se infiere un punto desde el barrio o la dirección: es preferible no tener ubicación a tener una inventada. Las dos constructoras usan esta función.

Cuando la ubicación aparece después:

- `ScrapeDeveloper._project`: si el proyecto guardado no tiene ubicación y la ficha ya trae una, se guarda con `CatalogRepository.update_project_location(project_id, location)`. Es el caso de Ezzenti el día que Londoño Gómez publique su mapa.
- Si el proyecto ya tenía ubicación y la ficha trae otra distinta, no se cambia: solo se registra en el log, como los cambios de área de las tipologías (SPEC 04).
- La API devuelve `location: null` para esos proyectos (`LocationOut | None` en `ProjectOut`).

### Constructora Capital (`infrastructure/scraping/constructora_capital.py`)

- `slug = "constructora-capital"`, el mismo de la semilla, para reutilizar la fila de la constructora.
- Slug de proyecto con prefijo `capital-` (`capital-verde-olivo`), decidido el 2 nov: los slugs son únicos entre constructoras y los de Capital son cortos (`axis`, `lino`). Solo cambia el slug; el nombre que ve el usuario sigue siendo el que extrae el modelo ("Verde Olivo"). Los proyectos de la semilla conservan su slug y se encuentran por `source_url`.
- Listado: `https://www.constructoracapital.com/proyectos/1/medellin-y-alrededores`. Los selectores exactos los confirma el paso 1 y se anotan en `docs/scrapers/constructora-capital.md`.
- Municipio: tabla determinista `CAPITAL_ZONES: dict[str, Municipality]` de la zona de la URL al municipio (`envigado` → `ENVIGADO`, `ciudad-del-rio` → `MEDELLIN`, `santa-ana` → `BELLO`, `niquia` → `BELLO`, y las demás que encuentre el paso 1). Una zona que no está en la tabla deja la ficha fuera de alcance y se registra en el log con aviso, para agregarla a mano.
- Fuera de alcance antes de pedir la ficha: zonas de Rionegro y títulos de proyectos que no son vivienda en venta (`office`, `renta`).
- Coordenadas: el patrón `lat,lon` del HTML y, si no está, el enlace de Waze, con `location_from_links`.
- Texto limpio: se quitan la sección de avances de obra (`#p_avances`) y la de otros proyectos (`#p_otrosproyectos`), para que el hash del texto sea estable. Las tarjetas de otros proyectos cambian al azar en cada carga y traen precios de otros proyectos (visto el 2 nov en Verde Olivo). Como el sitio no usa `<header>`, `<nav>` ni `<footer>`, el parser quita también `#header`, `#footer` y `#postfooter` por id.
- El prompt de extracción ya pide precios en pesos; la validación de rangos descarta los rangos de cuotas, los dólares y los SMMLV. Las tipologías que dicen "Consultar precios" quedan sin precio y no se guardan, como en Londoño Gómez.

### Reutilizar los proyectos y tipologías de la semilla

`CatalogRepository` suma `get_project_by_source_url(url: str) -> Project | None`. `ScrapeDeveloper._project` busca primero por slug y, si no lo encuentra, por `source_url`. Así, la ficha `.../262/axis` encuentra el proyecto `axis-ciudad-peldar` de la semilla, y su precio manual del 28 oct queda como primer punto del histórico, sin duplicar el proyecto.

Las tipologías se buscan en dos pasos dentro del proyecto:

1. Por nombre normalizado, como hoy.
2. Si no hay coincidencia, por área: una tipología existente con el mismo `built_area_m2` o el mismo `private_area_m2` (a dos decimales), siempre que haya **una sola** candidata. Así "Planta Apartamento 60.01 m2" encuentra el "Tipo 04" de la semilla (60,01 m² construidos) y su histórico sigue en la misma fila. Si hay cero o varias candidatas, se crea una tipología nueva y se registra en el log.

### Infraestructura

```hcl
variable "scrape_schedules" {
  type = map(string) # developer slug -> cron en hora de Bogotá
  default = {
    "londono-gomez"        = "cron(0 6 * * ? *)"
    "constructora-capital" = "cron(15 6 * * ? *)"
  }
}
```

`aws_scheduler_schedule.scraper` con `for_each = var.scrape_schedules` y `input = jsonencode({ developer = each.key, limit = null })`. Cada schedule se llama `sobreplano-scraper-{constructora}`. El schedule actual pasa con un bloque `moved` (de `aws_scheduler_schedule.scraper_daily` a `aws_scheduler_schedule.scraper["londono-gomez"]`); como cambia de nombre (`sobreplano-scraper-daily` → `sobreplano-scraper-londono-gomez`) y el nombre obliga a reemplazarlo, el recurso lleva `lifecycle { create_before_destroy = true }`, para que el nuevo exista antes de borrar el viejo. La variable `scrape_schedule` desaparece.

`reserved_concurrent_executions = 2` en la Lambda: con el límite de la cuenta en 40, AWS deja 38 sin reservar (el mínimo es 10). Dos es una corrida por constructora a la vez y limita el costo si algo se dispara. La regla de una corrida por constructora y día sigue en la base de datos.

## Plan de implementación

1. **Diagnóstico y exploración (sin código del proyecto).**
   - Bajar de S3 el HTML crudo de Primavela de dos días seguidos y compararlo con `diff`. Anotar qué cambia (tokens, fechas, orden) y confirmar con `clean_text` que el texto limpio de los dos días es idéntico. Si no lo es, quitar de `clean_text` lo que cambia.
   - Con `httpx` y el user-agent del proyecto, bajar una vez el listado y dos fichas de Constructora Capital a `data/raw/explore/` (Axis y Acento, que están en la semilla). Confirmar lo revisado en Chrome, anotar los selectores y completar la tabla de zonas con las 34 tarjetas del listado.
   - Buscar en la ficha de Ezzenti un enlace de Waze o un mapa embebido.
   - Resultados en `docs/scrapers/constructora-capital.md` y en el PR.
2. **Hash del texto.** `text_sha256`, migración `0004`, `ScrapeDeveloper` y `SqlScrapeRunRepository` usan la llave nueva. Test: dos páginas con HTML distinto y el mismo texto limpio reutilizan la extracción. Commit `fix:`.
3. **Tipologías.** `normalize_unit_type_name` con NFKC y `casefold`; `dedupe_unit_types` y su uso en `_record_prices`. Tests de los tres casos. Commit `fix:`.
4. **Ubicación con respaldo.** `geo_links.py` (Google, el patrón `lat,lon` suelto y Waze), `manual_locations.py` (vacía por ahora: Ezzenti queda sin ubicación) y el uso desde `LondonoGomezSite`. Migración `0005`, `Project.location` opcional, `update_project_location` y `location: null` en la API. Tests con HTML sintético para cada caso, uno que comprueba que cada entrada de `MANUAL_LOCATIONS` es un `GeoPoint` válido (rango del Valle de Aburrá), uno de un proyecto que se crea sin ubicación y la recibe en una corrida posterior, y uno de la API con `location: null`. Commit `fix:`.
5. **Semilla reutilizada.** `get_project_by_source_url` en el puerto y el repositorio, `ScrapeDeveloper._project` y la búsqueda de tipologías por área. Tests de integración: una ficha con la URL de un proyecto de la semilla no crea un proyecto nuevo, y una tipología con el área de la semilla reutiliza su fila. Commit `feat:`.
6. **Scraper de Capital.** `ConstructoraCapitalSite` con la tabla de zonas, los filtros y la limpieza de avances de obra; registro en `SITES`; tests con HTML sintético. Corrida local con `--dry-run` y luego real. Commit `feat:`.
7. **Terraform.** `scrape_schedules` con `for_each`, bloque `moved` y concurrencia reservada de 2. `terraform plan` debe mostrar 1 schedule nuevo (`constructora-capital`), 1 reemplazado con `create_before_destroy` (`londono-gomez`: `sobreplano-scraper-daily` → `sobreplano-scraper-londono-gomez`) y la Lambda modificada; ninguna otra destrucción. El `apply` se hace fuera de 5:45–6:30. **Esperar el OK de Andrés antes de `terraform apply`.** Commit `feat:`.
8. **Corrida en AWS.** Invocar la Lambda a mano para cada constructora y revisar los reportes. Commit `docs:` con la evidencia en `docs/deploy.md`.
9. **Documentación.** `docs/scrapers/constructora-capital.md`, la sección de reutilización en `docs/scrapers/londono-gomez.md`, `docs/deploy.md` con los dos schedules y `CLAUDE.md` con el comando de Capital. Commit `docs:`.

## Criterios de aceptación

Cada criterio se verifica pegando el comando y su salida en el PR (constitución, principio 6).

- [ ] El paso 1 está documentado: qué cambia en el HTML entre días, que el texto limpio de dos días es idéntico, los selectores de Capital y la tabla de zonas completa.
- [ ] `alembic upgrade head`, `downgrade -1` y `upgrade head` funcionan en local; `alembic check` limpio; `alembic heads` da una sola cabeza.
- [ ] La primera corrida de Londoño Gómez de un día reporta `0 already recorded today`.
- [ ] La segunda corrida de Londoño Gómez con la llave nueva (al día siguiente, en AWS) reporta `extractions: N reused` con N mayor que la mitad de las fichas, y gasta menos tokens que la del día anterior.
- [ ] Ezzenti queda en `projects` sin coordenadas (`location is null`) y deja de aparecer como fallida; un test demuestra que la ubicación se guarda cuando la ficha la publica.
- [ ] La corrida de Capital registra precios en al menos los 3 proyectos de la semilla y `select count(*) from projects where slug like '%ciudad-peldar%'` sigue en 3: no hay proyectos duplicados.
- [ ] Al menos una tipología de cada proyecto de la semilla que tenga precio en el sitio recibe una observación `scraper`: `select ut.name, count(*) from price_observations po join unit_types ut on ut.id = po.unit_type_id join projects p on p.id = ut.project_id where p.slug = 'axis-ciudad-peldar' group by ut.name` muestra filas con más de una observación.
- [ ] Ningún proyecto de Rionegro ni de Urbanity: `select count(*) from projects where slug ilike '%rosa%' or slug ilike '%urbanity%'` devuelve 0.
- [ ] `aws scheduler list-schedules --name-prefix sobreplano-scraper` muestra exactamente `sobreplano-scraper-londono-gomez` y `sobreplano-scraper-constructora-capital`, a las 6:00 y 6:15 (el viejo `-daily` ya no existe).
- [ ] `terraform plan` después del `apply` dice `No changes`.
- [ ] `curl -s "localhost:8000/projects" | jq '[.items[].developer.slug] | unique'` muestra las dos constructoras, con la API apuntando a la base en la nube.
- [ ] `uv run pytest -m "not integration"`, `uv run pyright` (0 errores) y `uv run lint-imports` (2 contratos) pasan; el CI del PR queda en verde.

## Decisiones tomadas y descartadas

- **Sí:** diagnosticar antes de corregir. El 2 nov las consultas a la base en la nube confirmaron las dos causas: el hash del HTML cambia cada día en las 21 fichas, y el "ya registrado" es una tipología de Verdeventura que el modelo devuelve dos veces idéntica. El segundo caso resultó menos grave de lo que se pensaba: no se perdía ningún precio.
- **Sí:** reutilizar por hash del texto limpio. Es exactamente lo que recibe el modelo: si el texto no cambió, la extracción tampoco. **No:** quitar del HTML los fragmentos dinámicos uno por uno, que se rompe cada vez que el sitio cambia su plantilla.
- **Sí:** mantener el hash del HTML para el nombre del archivo crudo. Identifica el archivo exacto, y cambiar la llave rompería la que comparten disco y S3.
- **Sí:** renombrar `page_extractions.content_sha256` a `text_sha256` en vez de crear otra columna. La columna vieja no tendría uso, y el nombre debe decir qué guarda.
- **No:** recalcular el hash de las extracciones viejas. Requeriría volver a limpiar el HTML de S3; una sola re-extracción cuesta medio centavo.
- **Sí:** diferenciar tipologías homónimas agregando el área al nombre. Cumple el único (`project_id`, `name`) sin migración. **No:** cambiar el único a nombre más áreas: si el sitio corrige un área, se crearía otra tipología y se partiría su histórico.
- **Sí:** el menor precio cuando la misma tipología aparece con dos precios. Los precios publicados son "desde".
- **Sí:** Waze como segundo respaldo y un archivo manual como último. **No:** un servicio de geocodificación, que cuesta, puede equivocarse de barrio y agrega una dependencia por un solo proyecto.
- **Sí:** guardar sin ubicación el proyecto cuya ficha no publica coordenadas, y completarla cuando la constructora la publique (decidido el 2 nov, caso Ezzenti). **No:** inferir un punto desde el barrio ("Calasanz, Medellín"): una ubicación inventada es peor que ninguna, y el scraper revisa la ficha todos los días.
- **Sí:** ubicaciones manuales como tabla en código, igual que `CAPITAL_ZONES`: se despliega con `src/`, no depende del directorio de trabajo y `GeoPoint` las valida al importar. **No:** `seeds/locations.json`, que exigía copiarlo en la imagen y agregarlo al workflow de despliegue. Si la tabla crece a decenas de entradas, pasar a un JSON del paquete con `importlib.resources`.
- **Sí:** buscar el proyecto por `source_url` para reutilizar la semilla. **No:** cambiar el slug de los proyectos de la semilla con una migración de datos; la URL de la ficha ya los identifica.
- **Sí:** un schedule por constructora con `for_each` y un bloque `moved`. Es una línea por constructora nueva.
- **Sí:** nombres uniformes `sobreplano-scraper-{constructora}`. Renombrar obliga a reemplazar el schedule, que no guarda estado; `create_before_destroy` evita que quede un momento sin schedule. **No:** un mapa de nombres heredados, que deja una excepción permanente por un recurso sin estado. El `apply` se hace fuera de 5:45–6:30. **No:** SQS todavía; con dos constructoras, dos schedules escalonados son más simples.
- **Sí:** escalonar 15 minutos. Una corrida dura menos de 2 minutos, así nunca se cruzan y la alarma dice cuál falló por la hora.
- **Sí:** concurrencia reservada de 2, ahora que la cuenta tiene límite 40. Limita el costo de un error que dispare invocaciones; la regla de una corrida por día sigue en la base de datos.
- **Sí:** `slug = "constructora-capital"`, el de la semilla, para no crear una segunda fila de la misma constructora.
- **Sí:** prefijo `capital-` en los slugs de proyecto de Capital. Evita que un proyecto nuevo choque con uno de otra constructora del mismo nombre. **No:** cambiar los slugs de Londoño Gómez, que ya están en la base.
- **Sí:** tabla determinista de zona a municipio para Capital, con aviso para zonas nuevas. **No:** pedirle el municipio al modelo; un barrio mal asignado arruinaría el precio por m² por zona.
- **Sí:** buscar tipologías por área cuando el nombre no coincide, solo si hay una candidata. Conecta la semilla con el scraper sin migraciones de datos. **No:** renombrar las tipologías de la semilla a mano.
- **Sí:** quitar los avances de obra del texto limpio. Cambian sin que cambien los precios, y harían que el hash del texto nunca se repita.
- **Sí:** quitar también la sección de otros proyectos del texto limpio (decidido el 2 nov). Sus tarjetas cambian en cada carga, lo que haría que el hash del texto nunca se repita, y sus precios "Desde" de otros proyectos podrían terminar en el histórico del proyecto equivocado.

## Riesgos identificados

| Riesgo | Mitigación |
| --- | --- |
| Capital publica precio solo para la tipología más barata | Es lo que publica el sitio; el histórico sigue esa tipología. Las demás quedan en el catálogo sin precio, como hoy en Londoño Gómez |
| Una zona nueva de Capital no está en la tabla | La ficha queda fuera con un aviso en el log, y se agrega a la tabla en un PR corto |
| La búsqueda por área une dos tipologías distintas que comparten un área | Solo une cuando hay una sola candidata; el log registra cada unión para revisarla |
| El texto limpio también cambia cada día (por ejemplo, una fecha o un contador visible) | El paso 1 lo ve en el `diff`. Si pasa, `clean_text` quita ese bloque y el cambio se documenta |
| La IA nombra distinto la misma tipología en días distintos ("Tipo 4" y "Tipo 04") | Se registra en el log cuando aparece una tipología nueva en un proyecto que ya tenía otras; el golden set del SPEC 09 medirá la estabilidad de los nombres |
| La primera corrida después del cambio de llave vuelve a extraer todo | Es una vez y cuesta medio centavo por constructora |
| El bloque `moved` no coincide y Terraform propone borrar el schedule actual sin crear el nuevo antes | El paso 7 exige revisar el plan: solo el reemplazo de `londono-gomez` con `create_before_destroy`, ninguna otra destrucción |
| Una tipología de Capital no coincide con la de la semilla por una diferencia de nombre | El criterio de conteo lo detecta; si pasa, se agrega el alias en el test y se ajusta la normalización |

## Lo que **no** entra en este spec

- SQS, `/add-scraper` y más constructoras.
- Cobertura fuera del Valle de Aburrá.
- Alianzas entre constructoras.
- Precio "desde" por proyecto.
- Re-extraer el histórico.
- Playwright.
- API de lectura.

Cada uno, si llega, va en su propio spec.
