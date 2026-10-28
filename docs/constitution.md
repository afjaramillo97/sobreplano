# Constitución de Sobreplano

Versión 1.1.0 · 2026-10-28

Este documento manda sobre `CLAUDE.md` si ambos se contradicen. Todo spec debe cumplirlo; un spec que lo viole se corrige o enmienda esta constitución primero (con entrada en el changelog).

Cada principio trae la regla o el comando que lo verifica. Las rutas de ejemplo (`src/sobreplano/domain/`, `src/sobreplano/application/`) las fija el SPEC 01.

## 1. Las capas dependen en una sola dirección

`interface → application → domain`; `infrastructure` implementa los puertos de `domain`. `domain` y `application` no importan `sqlalchemy` ni `fastapi`.

Verifica: `uv run lint-imports` reporta todos los contratos cumplidos (capas, y sin `sqlalchemy` ni `fastapi` en `domain` y `application`).

## 2. Las observaciones de precio son append-only

Una observación de precio nunca se actualiza ni se borra. La API del repositorio solo expone `add` y lecturas; no existe `update` ni `delete` para observaciones. La base de datos lo hace cumplir con un trigger, así que la regla también vale para `psql` y para cualquier script.

Verifica: dos tests. Uno unitario confirma que el repositorio no expone `update` ni `delete`. Otro de integración confirma que la base de datos rechaza `UPDATE`, `DELETE` y `TRUNCATE` sobre `price_observations` (`uv run --env-file .env pytest tests/unit/infrastructure tests/integration/test_db_rules.py`).

## 3. Scraping responsable

Se respeta `robots.txt`, una visita por sitio al día, user-agent `SobreplanoBot/0.1 (+https://github.com/afjaramillo97/sobreplano)`, HTML crudo guardado en S3 y ningún dato personal.

Verifica: test del scraper que lee `robots.txt` antes de visitar, test que comprueba el user-agent, y revisión del esquema: ninguna columna con datos personales.

## 4. Fronteras tipadas

Pydantic en los bordes: entrada y salida de la API, de las herramientas del asesor y de la extracción con LLM. Todo el código Python pasa pyright en modo estricto.

Verifica: `uv run pyright` (con `typeCheckingMode = "strict"`) termina con 0 errores.

## 5. Toda llamada a un LLM registra modelo y tokens

Aplica desde la semana 3. Cada llamada guarda el modelo usado y los tokens de entrada y salida.

Verifica: test que ejecuta la extracción con un cliente falso y comprueba que el registro contiene `model`, `input_tokens` y `output_tokens`.

## 6. Evidencia sobre afirmaciones

Nada está terminado hasta que el comando se ejecutó y se leyó su salida. Un spec o PR no dice "funciona" sin mostrar el comando y su resultado.

Verifica: la sección de verificación de cada spec lista comandos concretos; el PR pega su salida.

## 7. Los specs se escriben contra el código actual

Antes de escribir un spec se lee el código y los specs vigentes; no se asumen archivos, funciones ni esquemas que no existen.

Verifica: cada spec cita rutas reales (`archivo:línea`) del código que toca; `ls` y `grep` confirman que existen.

## Changelog

- **1.1.0** (2026-10-28): la verificación del principio 2 pasa del `grep` de `UPDATE|DELETE` (daba falso positivo con el propio trigger y es más débil) a dos tests: el repositorio no expone `update` ni `delete`, y la base de datos rechaza `UPDATE`, `DELETE` y `TRUNCATE`. Spec: `specs/02-schema-v1.md`.
- **1.0.1** (2026-10-26): la verificación del principio 1 pasa de `grep` a `uv run lint-imports` (import-linter detecta también imports indirectos); las rutas de ejemplo apuntan a `src/sobreplano/`. Spec: `specs/01-python-foundations.md`.
- **1.0** (2026-10-26): versión inicial con siete principios.
