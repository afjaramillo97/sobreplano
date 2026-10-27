# SPEC 01 — Fundaciones del proyecto Python

> **Estado:** implementado
> **Depende de:** ninguno
> **Fecha:** 2026-10-26
> **Objetivo:** Crear el paquete Python `sobreplano` con sus cuatro capas y los controles de calidad (ruff, pyright strict, pytest, import-linter) que cada PR debe pasar en CI.

## Por qué existe este spec

La constitución v1.0 (`docs/constitution.md`) define reglas verificables (capas, tipado estricto) pero el repo aún no tiene código ni herramientas que las hagan cumplir. Este spec fija el suelo sobre el que se construyen el esquema (SPEC 02), la API (SPEC 03) y los scrapers: sin él, cada spec posterior tendría que decidir estructura y controles por su cuenta.

Estado actual del repo (confirmado antes de escribir): existen `CLAUDE.md`, `README.md`, `docs/constitution.md`, `.gitignore` y `.claude/skills/`. No existen `pyproject.toml`, `src/`, `tests/`, `.github/` ni `.claude/settings.json`. El `.gitignore` ya excluye `.venv`, `.ruff_cache/` y `.pytest_cache/`, y no excluye `uv.lock` ni `.python-version`.

## Alcance
/
**Dentro:**

- `pyproject.toml` con `requires-python = ">=3.13"`, `.python-version` en `3.13` y `uv.lock` versionado.
- Paquete `src/sobreplano/` con las capas `domain/`, `application/`, `infrastructure/` e `interface/`, solo con `__init__.py`.
- `tests/` en la raíz, con un test de humo por capa que importa el paquete.
- Configuración de ruff (lint y formato) y pyright en modo `strict` dentro de `pyproject.toml`.
- Dos contratos de import-linter en `pyproject.toml`: capas y prohibición de `sqlalchemy`/`fastapi` en `domain` y `application`.
- Workflow `.github/workflows/ci.yml` que ejecuta los cinco controles en cada PR hacia `main` y en cada push a `main`.
- Enmienda de la constitución a v1.0.1: la verificación del principio 1 pasa de `grep` a `uv run lint-imports`.
- `.claude/settings.json` versionado con un hook que corre ruff sobre los archivos Python editados y con los plugins `security-guidance` y `pyright-lsp` habilitados.
- Actualizar `CLAUDE.md` con los comandos de build/test y el layout del paquete.
- `specs/.spec-config.yml` (configuración del flujo de specs).

**Fuera de alcance (para specs futuros):**

- Entidades de dominio, puertos, casos de uso y adaptadores: el esquema y el modelo llegan en SPEC 02.
- SQLAlchemy, Alembic y el skill `postgres-best-practices`: SPEC 02.
- FastAPI y el skill de FastAPI: SPEC 03.
- Scrapers, Playwright, Docker/Lambda, Terraform e Infracost.
- Carpetas `api/`, `scrapers/`, `advisor/`, `web/`, `infra/`, `migrations/` y `evals/` de la estructura planeada en `CLAUDE.md`.
- Branch protection de `main` (ajuste en GitHub, fuera del repo).
- `pre-commit` local.
- Umbral de cobertura de tests.
- Convención de ramas (sigue pendiente en `CLAUDE.md`).

## Modelo de datos

Este spec no introduce estructuras de datos. Fija la estructura de carpetas y la configuración de herramientas.

```
sobreplano/
├── .claude/
│   ├── hooks/ruff-edited.sh
│   └── settings.json
├── .github/workflows/ci.yml
├── .python-version
├── pyproject.toml
├── uv.lock
├── specs/.spec-config.yml
├── src/sobreplano/
│   ├── __init__.py
│   ├── domain/__init__.py          entidades y puertos (typing.Protocol)
│   ├── application/__init__.py     casos de uso
│   ├── infrastructure/__init__.py  SQLAlchemy, Playwright, Anthropic, S3
│   └── interface/__init__.py       FastAPI, handler de Lambda, servidor MCP
└── tests/
    └── test_layers.py
```

Convenciones:

- Se importa como `sobreplano.domain`, `sobreplano.application`, etc. (src layout, paquete instalado en modo editable por `uv sync`).
- `tests/` vive fuera de `src/` y no se empaqueta.

Configuración de ruff (forma, no texto final):

```toml
[tool.ruff]
line-length = 100
target-version = "py313"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "UP", "B", "SIM", "RUF"]
```

Contratos de import-linter (forma, no texto final):

```toml
[tool.importlinter]
root_package = "sobreplano"
include_external_packages = true

[[tool.importlinter.contracts]]
name = "Layers"
type = "layers"
layers = ["sobreplano.interface", "sobreplano.application | sobreplano.infrastructure", "sobreplano.domain"]

[[tool.importlinter.contracts]]
name = "No framework in domain/application"
type = "forbidden"
source_modules = ["sobreplano.domain", "sobreplano.application"]
forbidden_modules = ["sqlalchemy", "fastapi"]
```

La barra `|` hace que `application` e `infrastructure` sean hermanas: ninguna importa a la otra, y ambas dependen de `domain`. `interface` puede importar de las dos (es la raíz de composición).

## Plan de implementación

1. Crear `pyproject.toml` (nombre `sobreplano`, `requires-python = ">=3.13"`, backend `uv_build`, grupo de dependencias `dev`), `.python-version` y `src/sobreplano/__init__.py`. Ejecutar `uv sync`; versionar `uv.lock`.
2. Crear los cuatro subpaquetes de capa con `__init__.py` y `tests/test_layers.py` (un test por capa que importa el subpaquete). `uv run pytest` pasa.
3. Agregar ruff al grupo `dev` y su configuración (`line-length = 100`, `target-version = "py313"`, `select = ["E", "F", "W", "I", "UP", "B", "SIM", "RUF"]`). `uv run ruff check` y `uv run ruff format --check` pasan.
4. Agregar pyright al grupo `dev` con `typeCheckingMode = "strict"` e `include = ["src", "tests"]`. `uv run pyright` termina con 0 errores.
5. Agregar import-linter al grupo `dev` y los dos contratos. `uv run lint-imports` pasa.
6. Enmendar `docs/constitution.md`: versión 1.0.1, verificación del principio 1 = `uv run lint-imports`, rutas de ejemplo de la línea 7 apuntando a `src/sobreplano/`, entrada en el changelog.
7. Crear `.github/workflows/ci.yml`: en `pull_request` hacia `main` y en `push` a `main`, instala uv, `uv sync --locked` y corre ruff check, ruff format --check, pyright, pytest y lint-imports.
8. Crear `.claude/hooks/ruff-edited.sh` y `.claude/settings.json` (hook `PostToolUse` sobre `Edit|Write|MultiEdit` que corre `uv run ruff check --fix` y luego `uv run ruff format` sobre el archivo `.py` editado, y `enabledPlugins` con `security-guidance` y `pyright-lsp`). Confirmar los identificadores exactos de los plugins con `/plugin` antes de escribirlos.
9. Actualizar `CLAUDE.md`: comandos de build/test, layout `src/sobreplano/`, y quitar esos puntos de la sección TBD. Además, corregir la línea "Code, commits and docs stay in English" para que coincida con la excepción de `specs/` y `docs/constitution.md`, que están en español. Crear `specs/.spec-config.yml` si no existe.

Cada paso deja el repo ejecutable y es commiteable por separado (Conventional Commits: `chore:` para 1, 3-5 y 7-9; `test:` para 2; `docs:` para 6).

## Criterios de aceptación

Cada criterio se verifica pegando el comando y su salida en el PR (constitución, principio 6).

- [ ] `uv sync --locked` termina con código 0 y `uv.lock` está versionado.
- [ ] `cat .python-version` imprime `3.13`.
- [ ] `uv run python -c "import sobreplano.domain, sobreplano.application, sobreplano.infrastructure, sobreplano.interface"` termina sin error.
- [ ] `uv run pytest` ejecuta al menos 4 tests y todos pasan.
- [ ] `uv run ruff check` y `uv run ruff format --check` terminan con código 0.
- [ ] `uv run pyright` termina con 0 errores y `pyproject.toml` contiene `typeCheckingMode = "strict"`.
- [ ] `uv run lint-imports` reporta 2 contratos cumplidos, 0 rotos.
- [ ] Prueba negativa: agregar temporalmente `import sqlalchemy` en `src/sobreplano/domain/__init__.py` hace que `uv run lint-imports` falle; se revierte antes de commitear.
- [ ] Prueba negativa: agregar temporalmente `import sobreplano.infrastructure` en `src/sobreplano/domain/__init__.py` hace que `uv run lint-imports` falle; se revierte antes de commitear.
- [ ] Prueba negativa: agregar temporalmente `import sobreplano.infrastructure` en `src/sobreplano/application/__init__.py` hace que `uv run lint-imports` falle (capas hermanas); se revierte antes del commit final.
- [ ] `docs/constitution.md` dice `Versión 1.0.1`, el principio 1 verifica con `uv run lint-imports`, el changelog tiene la entrada 1.0.1 y `grep -n "grep -rEn" docs/constitution.md` ya no devuelve el principio 1.
- [ ] El PR de prueba hacia `main` lleva primero un commit con una violación de capas, con el CI en rojo en el paso `lint-imports`, y luego un commit que la revierte, con el CI en verde en los cinco pasos. Los enlaces de las dos ejecuciones van en el PR.
- [ ] `.claude/settings.json` es JSON válido (`python3 -m json.tool .claude/settings.json`) y declara los plugins `security-guidance` y `pyright-lsp`.
- [ ] Tras editar un `.py` mal formateado en una sesión de Claude Code, el archivo queda formateado por ruff sin intervención; editar un `.md` no ejecuta ruff.
- [ ] `CLAUDE.md` documenta los comandos `uv sync`, `uv run ruff check`, `uv run ruff format --check`, `uv run pyright`, `uv run pytest` y `uv run lint-imports`.
- [ ] `git status` no muestra `.venv`, `.ruff_cache` ni `.pytest_cache` sin ignorar.

## Decisiones tomadas y descartadas

- **Sí:** un solo paquete `src/sobreplano/` con src layout. Los servicios futuros (API, scrapers, advisor) son composiciones sobre las mismas capas, no paquetes separados. Evita imports rotos por estar fuera de `src/`.
- **No:** carpetas de capas en la raíz del repo. Chocan con la estructura planeada (`api/`, `scrapers/`, `advisor/`) y ensucian la raíz.
- **No:** workspace uv con varios paquetes. Sobreingeniería en la semana 2.
- **Sí:** import-linter como único mecanismo de verificación de capas, con un contrato `layers` y uno `forbidden` con `include_external_packages = true`. El contrato `forbidden` detecta también imports indirectos, que un `grep` no ve.
- **No:** mantener el `grep` de la constitución junto a import-linter. Duplica la verificación y el `grep` es más débil; por eso se enmienda el principio 1 (v1.0.1).
- **Sí:** `application` e `infrastructure` como capas hermanas (`|`). `infrastructure` implementa puertos de `domain`; `application` no debe conocer adaptadores.
- **Sí:** Python 3.13. Versión madura (octubre de 2024), con wheels en todo el stack actual; Lambda soporta python3.13 hasta el 30 de junio de 2029.
- **Sí:** solo esqueleto y tests de humo, sin entidades ni slice de ejemplo. El modelo de datos pertenece a SPEC 02.
- **Sí:** pyright como dependencia `dev` en uv además del plugin `pyright-lsp`. CI y la constitución (principio 4) verifican con `uv run pyright`; el plugin solo da feedback en el editor.
- **Sí:** `uv_build` como backend de build. Es el backend por defecto de uv para src layout y no agrega otra herramienta.
- **Sí:** un único job de CI con pasos secuenciales. El proyecto es chico; paralelizar no ahorra tiempo apreciable ni minutos de Actions.
- **Sí:** hook y plugins en `.claude/settings.json` versionado, para que cualquier sesión del repo los herede.
- **No:** branch protection ni `pre-commit` en este spec. El primero es un ajuste manual en GitHub que se hace una vez que el check `ci` exista; el segundo duplica el CI.
- **Sí:** los skills `postgres-best-practices` (SPEC 02) y de FastAPI (SPEC 03) se instalan en el spec que los necesita, no antes.

## Riesgos identificados

| Riesgo | Mitigación |
| --- | --- |
| Los identificadores de los plugins `security-guidance` y `pyright-lsp` no coinciden con lo escrito en `enabledPlugins`. | El paso 8 exige confirmarlos con `/plugin` antes de escribir el archivo. |
| `pyright-lsp` necesita el binario de pyright disponible. | Pyright queda en el grupo `dev` de uv; `uv sync` lo instala. |
| El hook depende de `jq` para leer el archivo editado. | El script sale con código 0 si no puede leer la ruta o si no es `.py`; nunca bloquea la edición. Si `jq` falta, se documenta en `CLAUDE.md`. |
| Pyright strict choca con librerías sin tipos (Playwright, LangGraph) cuando lleguen. | Se resuelve por spec con stubs o `# pyright: ignore[...]` acotado; nunca bajando `typeCheckingMode` global. |
| Alguien agrega un import prohibido en una capa y el contrato no lo detecta por mal configurado. | Las tres pruebas negativas de los criterios de aceptación demuestran que los contratos fallan cuando deben. |
| Python 3.13 sin wheel para una dependencia futura. | Se detecta en `uv sync` del spec que la agregue; ese spec decide fijar versión o bajar a 3.12 con enmienda. |

## Lo que **no** entra en este spec

- Entidades, puertos, casos de uso y adaptadores (SPEC 02 en adelante).
- Base de datos, SQLAlchemy y Alembic.
- API, scrapers, asesor y frontend.
- Docker, Lambda, Terraform y Infracost.
- Branch protection, `pre-commit` y umbrales de cobertura.
- Los skills `postgres-best-practices` y de FastAPI.

Cada uno, si llega, va en su propio spec.
