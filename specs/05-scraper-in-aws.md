# SPEC 05 — El scraper corre solo cada día en AWS

> **Estado:** implementado
> **Depende de:** SPEC 02, SPEC 04
> **Fecha:** 2026-10-31
> **Objetivo:** Que el scraper de Londoño Gómez corra todos los días a las 6:00 a. m. (hora de Bogotá) en una Lambda de AWS creada con Terraform, guardando el HTML crudo en S3 y los datos en Supabase en la nube, sin que nadie lo ejecute a mano.

## Por qué existe este spec

El histórico de precios empezó el 30 de octubre, pero hoy depende de que Andrés corra el scraper en su Mac cada mañana. Un día que no corre es un dato perdido para siempre. Este spec lo vuelve automático y deja la base de datos en la nube, donde la usarán la API y el asesor.

Estado actual del repo (`main` en `2e6991e`):

- `src/sobreplano/interface/cli/scrape.py:35-63` arma el caso de uso `ScrapeDeveloper` con `HttpFetcher`, `FileRawPageStore`, el extractor y los repositorios SQL, en una sola transacción.
- `src/sobreplano/infrastructure/scraping/file_store.py` guarda en `data/raw/{developer}/{YYYY-MM-DD}/{sha256}.html`; su docstring ya anuncia el cambio a S3.
- `src/sobreplano/domain/ports.py:52-55`: `RawPageStore.save(developer_slug, page) -> str`.
- `src/sobreplano/infrastructure/settings.py`: `database_url`, `extraction_model` y `openai_api_key`.
- `src/sobreplano/infrastructure/db/engine.py:24`: `create_engine(url)` sin opciones de conexión.
- No existen `infra/`, `Dockerfile` ni workflow de despliegue.
- El histórico del 30 y 31 de octubre vive solo en la base de datos local y en `data/raw/`.

Datos verificados el 31 oct en la documentación oficial:

- Supabase: la conexión directa es solo IPv6 en los planes Free y Pro. Desde una red solo IPv4, como una Lambda fuera de VPC, hay que usar el pooler compartido. Para funciones serverless recomienda el modo transacción (puerto 6543), que no soporta prepared statements.
- EventBridge Scheduler acepta cron con zona horaria IANA (`America/Bogota`). Bogotá no tiene horario de verano.
- Terraform: el backend S3 bloquea el estado con `use_lockfile = true`; el bloqueo con DynamoDB está obsoleto.
- Lambda: imagen base `public.ecr.aws/lambda/python:3.13` (Amazon Linux 2023, soporte hasta el 30 de junio de 2029), con soporte para arm64.

## Alcance

**Dentro:**

- Región `us-east-1` para AWS y para el proyecto de Supabase en la nube.
- Bucket de estado de Terraform creado una vez a mano (versionado y cifrado), con `use_lockfile`.
- Terraform en `infra/`: bucket S3 privado para el HTML crudo, repositorio ECR, Lambda con imagen de contenedor arm64, rol IAM con permisos mínimos, EventBridge Scheduler diario, grupo de logs con 14 días de retención, alarma de errores con aviso por correo, presupuesto mensual con aviso, y rol para GitHub Actions por OIDC.
- Secretos (`DATABASE_URL` y `OPENAI_API_KEY`) en SSM Parameter Store como `SecureString`, creados a mano. Terraform solo conoce sus nombres, así los valores nunca quedan en el estado.
- `S3RawPageStore` en `infrastructure/scraping/s3_store.py`, con la misma llave que el almacén en disco.
- Composición compartida entre el CLI y la Lambda en `interface/composition.py`.
- Handler `interface/lambda_handler.py`.
- Conexión por el pooler en modo transacción, con prepared statements apagados.
- Una sola corrida por constructora y día, garantizada en la base de datos: candado `pg_try_advisory_xact_lock` por constructora y salto si ya hay una corrida `succeeded` hoy. Estado nuevo `skipped` (migración `0003`) y `--force` en el CLI.
- `Dockerfile` en la raíz, con solo las dependencias de runtime.
- Supabase en la nube con las migraciones aplicadas y el histórico local copiado.
- Workflow `.github/workflows/deploy-scraper.yml`: en cada push a `main` que toque `src/`, el `Dockerfile` o `uv.lock`, construye la imagen, la sube a ECR y actualiza la Lambda.
- Job de CI con `terraform fmt -check` y `terraform validate`.

**Fuera de alcance (para specs futuros):**

- SQS y varias constructoras: SPEC 06.
- LocalStack, Infracost y `terraform plan` en los PR: SPEC 11.
- `terraform apply` desde GitHub Actions: se aplica en local, según la regla de "preguntar antes de lo que cuesta dinero".
- Desplegar la API: SPEC 14.
- Playwright en Lambda.
- Ambientes separados (staging): solo hay producción.

## Modelo de datos

El único cambio de esquema es el estado `skipped` en el CHECK de `scrape_runs.status` (migración `0003`). El resto es configuración e infraestructura.

### Una corrida por constructora y día

`ScrapeDeveloper`, al iniciar y antes de cualquier petición HTTP:

1. Toma `pg_try_advisory_xact_lock` con una llave derivada del `developer_id`, a través de un método de `ScrapeRunRepository` (`application` no importa SQLAlchemy). Si no lo obtiene, otra corrida está en curso: termina `skipped`.
2. Si ya hay una `scrape_run` `succeeded` de esa constructora con `run_on` de hoy (Bogotá), termina `skipped`. El CLI tiene `--force` para saltarse esta regla en desarrollo; el candado no se salta nunca.

Se usa la versión `xact` porque el pooler en modo transacción no conserva candados de sesión; la corrida entera es una transacción. Una corrida `skipped` deja su fila en `scrape_runs` con la razón en `error`.

### Configuración (`infrastructure/settings.py`)

```python
class Settings(BaseSettings):
    database_url: str = Field(min_length=1)
    extraction_model: str = "openai:gpt-6-luna"
    openai_api_key: SecretStr | None = None
    # "data/raw" (default, local disk) or "s3://bucket-name"
    raw_store: str = "data/raw"
```

En la Lambda, el handler lee los dos secretos de SSM al arrancar (una sola llamada `get_parameters` con descifrado) y los pasa a `Settings`. Los nombres de los parámetros llegan como variables de entorno: `SSM_DATABASE_URL=/sobreplano/prod/database_url` y `SSM_OPENAI_API_KEY=/sobreplano/prod/openai_api_key`.

### Conexión a la base de datos

`create_db_engine()` agrega `connect_args={"prepare_threshold": None}` cuando la URL apunta al puerto 6543 (pooler en modo transacción), y usa `poolclass=NullPool` dentro de la Lambda. Así no se reutilizan conexiones entre invocaciones congeladas y no se crean prepared statements que el pooler rechaza.

| Uso | Conexión | Puerto |
| --- | --- | --- |
| Lambda | Pooler compartido, modo transacción | 6543 |
| Migraciones con Alembic desde el Mac | Pooler compartido, modo sesión | 5432 |
| Desarrollo local | Supabase local | 54322 |

### Llaves en S3

Las mismas que en disco: `s3://{bucket}/{developer}/{YYYY-MM-DD}/{sha256}.html`, con `ContentType: text/html; charset=utf-8`. El bucket bloquea todo acceso público, cifra con SSE-S3 y mueve los objetos a Glacier Instant Retrieval a los 90 días.

### Evento de la Lambda

```json
{"developer": "londono-gomez", "limit": null}
```

La respuesta es el `ScrapeReport` en JSON (`succeeded` o `skipped`). El mismo resumen sale en los logs. Si la corrida termina `failed`, el handler lanza una excepción para que la Lambda cuente un error, la alarma avise y haya reintentos.

### Infraestructura (`infra/`)

| Archivo | Recursos |
| --- | --- |
| `versions.tf` | Terraform y proveedor AWS fijados; backend S3 con `use_lockfile = true` |
| `storage.tf` | Bucket del HTML crudo y su regla de ciclo de vida |
| `ecr.tf` | Repositorio `sobreplano-scraper` que conserva las últimas 5 imágenes |
| `lambda.tf` | Lambda `sobreplano-scraper` (arm64, 512 MB, timeout de 10 min, sin concurrencia reservada), rol y grupo de logs |
| `schedule.tf` | Schedule `cron(0 6 * * ? *)` en `America/Bogota`, 2 reintentos |
| `alerts.tf` | Tópico SNS por correo, alarma sobre `Errors >= 1` de la Lambda y presupuesto de 5 USD al mes |
| `github_oidc.tf` | Proveedor OIDC de GitHub y rol que solo puede subir a ese ECR y actualizar esa Lambda, limitado a `repo:afjaramillo97/sobreplano:ref:refs/heads/main` |
| `variables.tf`, `outputs.tf` | Correo de alertas, región, nombres de los parámetros SSM |

## Plan de implementación

1. **Requisitos (manual, sin código).** La cuenta de AWS ya está lista: todo se crea en la cuenta miembro `sobreplano-prod` con el perfil SSO `sobreplano-prod` (`docs/aws-accounts.md`). Proyecto de Supabase en `us-east-1`. Bucket de estado (`aws s3api create-bucket`, versionado y bloqueo de acceso público). Parámetros SSM con `scripts/sync-ssm-secrets.sh`, que los lee de `.env` y `.env.cloud`. Andrés hace los tres pasos y anota los nombres en `docs/deploy.md`.
2. **Base de datos en la nube.** `alembic upgrade head` contra Supabase por el pooler en modo sesión. Copiar el histórico local con `pg_dump --data-only` de `developers`, `projects`, `unit_types`, `price_observations`, `scrape_runs`, `scraped_pages` y `page_extractions`, y cargarlo con `psql`. Verificar que los conteos coinciden. Commit `docs:` con los comandos en `docs/deploy.md`.
3. **Conexión por el pooler.** `engine.py` con `prepare_threshold=None` para el puerto 6543 y `NullPool` opcional. Test unitario de los argumentos del motor. Commit `feat:`.
4. **Almacén en S3.** `uv add boto3` y `S3RawPageStore` con la misma llave que el de disco. `Settings.raw_store` y una fábrica que elige disco o S3. Test con un cliente de S3 falso, sin red. `boto3` y `botocore` entran a `forbidden_modules`. Commit `feat:`.
5. **Composición y handler.** Mover el armado de `scrape()` a `interface/composition.py`, sin cambiar el comportamiento del CLI. `interface/lambda_handler.py` lee SSM, arma `Settings`, corre la composición y devuelve el reporte. Test del handler con un SSM falso y fakes de los puertos. Commit `refactor:` y luego `feat:`.
6. **Imagen.** `Dockerfile` sobre `public.ecr.aws/lambda/python:3.13`: `uv export --no-dev` a requirements, instalación y copia de `src/`. `.dockerignore` excluye `data/`, `.venv/`, `tests/` y `.env`. Build local con `--platform linux/arm64 --provenance=false` y prueba con el emulador incluido en la imagen. Commit `feat:`.
6b. **Una corrida por constructora y día.** `ScrapeRunStatus.SKIPPED` y migración `0003` con el CHECK nuevo, escrita a mano. `ScrapeRunRepository.try_lock` y `has_succeeded`. `ScrapeDeveloper` termina `skipped` sin peticiones si no obtiene el candado o si ya hubo una corrida `succeeded` hoy; `--force` en el CLI. El handler solo lanza excepción con `failed`. Tests de integración: dos sesiones simultáneas (la segunda queda `skipped`) y segunda corrida del día (`skipped` sin llamar al fetcher). Commit `feat:`.
7. **Terraform.** Los archivos de `infra/`. `terraform fmt -check` y `terraform validate`. Mostrar `terraform plan` y **esperar el OK de Andrés antes de `terraform apply`**. Commit `feat:`.
8. **Primera imagen y corrida manual.** Subir la imagen a ECR, actualizar la Lambda y correr `aws lambda invoke` con `{"developer": "londono-gomez"}`. Revisar el reporte, los logs, los objetos en S3 y la fila nueva en `scrape_runs` de la nube. Commit `docs:` con la evidencia en `docs/deploy.md`.
9. **Despliegue con OIDC y CI de Terraform.** `deploy-scraper.yml` asume el rol por OIDC (sin llaves de AWS en GitHub), construye, sube y actualiza la Lambda. En `ci.yml`, un job con `terraform fmt -check` y `terraform validate`, sin backend ni credenciales (`terraform init -backend=false`). Commit `chore:`.
10. **Documentación.** `docs/deploy.md` completo (requisitos, migraciones, despliegue y cómo revisar una corrida); `CLAUDE.md` con `infra/` y los comandos; README con la arquitectura real. Commit `docs:`.

## Criterios de aceptación

Cada criterio se verifica pegando el comando y su salida en el PR (constitución, principio 6).

- [ ] `terraform -chdir=infra fmt -check` y `terraform -chdir=infra validate` pasan, también en CI.
- [ ] `terraform -chdir=infra plan` después del `apply` dice `No changes`.
- [ ] `grep -rn "openai_api_key\|database_url" infra/*.tf` solo muestra nombres de parámetros SSM, nunca valores; `terraform -chdir=infra state pull | grep -c "sk-"` imprime `0`.
- [ ] Los conteos de `developers`, `projects`, `unit_types` y `price_observations` en la nube son iguales a los locales después de la copia.
- [ ] `aws lambda invoke --function-name sobreplano-scraper --payload '{"developer":"londono-gomez"}' --cli-binary-format raw-in-base64-out out.json` termina con `"status": "succeeded"` en `out.json`.
- [ ] Una segunda invocación el mismo día termina `skipped` y no hace peticiones HTTP.
- [ ] `aws s3 ls s3://{bucket}/londono-gomez/ --recursive | wc -l` es mayor que 0 después de la corrida.
- [ ] `aws scheduler get-schedule --name sobreplano-scraper-daily` muestra `cron(0 6 * * ? *)` y `America/Bogota`.
- [ ] Al día siguiente, sin intervención, `scrape_runs` en la nube tiene una fila con `run_on` de ese día y `status = 'succeeded'`.
- [ ] Un push a `main` que toca `src/` ejecuta `deploy-scraper.yml` en verde, y la Lambda queda con la imagen de ese commit (`aws lambda get-function` muestra el digest nuevo).
- [ ] Los secretos del repo en GitHub no incluyen llaves de AWS: solo el ARN del rol, si hace falta.
- [ ] `uv run pytest -m "not integration"`, `uv run pyright` (0 errores) y `uv run lint-imports` (2 contratos) pasan.
- [ ] El presupuesto de 5 USD y la alarma de errores existen y el correo de suscripción a SNS está confirmado.

## Decisiones tomadas y descartadas

- **Sí:** pooler compartido de Supabase en modo transacción para la Lambda. La conexión directa es solo IPv6 en el plan gratuito y una Lambda fuera de VPC solo sale por IPv4. **No:** el complemento IPv4 de Supabase, que es de pago, ni meter la Lambda en una VPC, que obligaría a pagar un NAT Gateway (unos 32 USD al mes).
- **Sí:** `prepare_threshold=None` en psycopg con el puerto 6543. El pooler en modo transacción no soporta prepared statements.
- **Sí:** modo sesión (5432) para las migraciones desde el Mac. Alembic abre una conexión larga y la migración `0001` crea funciones y triggers; el modo sesión se comporta como una conexión normal.
- **Sí:** `us-east-1` para AWS y Supabase. Es la región más barata, las dos plataformas la tienen y quedan en la misma región, con menos latencia entre la Lambda y la base de datos.
- **Sí:** EventBridge Scheduler directo a la Lambda. **No:** SQS en este spec; con una sola constructora no reparte nada. Entra en SPEC 06, una Lambda por constructora.
- **Sí:** arm64. Es más barato por segundo en Lambda y el Mac M1 construye arm64 de forma nativa.
- **Sí:** una corrida por constructora y día garantizada en la base: candado `pg_try_advisory_xact_lock` por constructora y salto si ya hubo una corrida `succeeded` hoy, con estado `skipped`. La cuenta es nueva y tiene un límite de 5 ejecuciones concurrentes de Lambda; AWS exige dejar 10 sin reservar, así que la concurrencia reservada no se puede usar. La regla en la base no depende de la cuota, cubre también el CLI y se puede probar. **No:** concurrencia reservada en 1, ni siquiera cuando se apruebe el aumento de cuota pedido el 1 de noviembre.
- **Sí:** timeout de 10 minutos y 512 MB. Una corrida en local toma unos 2 minutos (25 fichas con 2 s de pausa más la extracción); el margen cubre sitios lentos. La cuenta nueva limita la memoria a 512 MB (`CreateFunction` rechazó 1024 el 1 de noviembre), y la corrida pasa casi todo el tiempo esperando la red y el LLM. La primera corrida en AWS mide `Max Memory Used`. **No:** 1024 MB, el valor original.
- **Sí:** reintentos en el Scheduler. Una corrida `failed` se puede reintentar sin duplicar (`ALREADY_RECORDED` y extracciones reutilizadas), y una vez hay una `succeeded` en el día, los reintentos terminan `skipped` sin visitar el sitio.
- **Sí:** secretos en SSM Parameter Store, creados a mano. El nivel estándar es gratis y los valores nunca pasan por el estado de Terraform. **No:** Secrets Manager, que cobra por secreto.
- **Sí:** el handler lee SSM al arrancar con boto3. **No:** la extensión de Lambda para parámetros; para dos valores por día no hace falta.
- **Sí:** `NullPool` en la Lambda. El pooler de Supabase ya reutiliza conexiones; un pool dentro de una Lambda congelada solo deja conexiones colgadas.
- **Sí:** `terraform apply` en local y despliegue de la imagen por GitHub Actions con OIDC. El código cambia seguido y la infraestructura casi nunca; aplicar Terraform requiere el OK de Andrés (`CLAUDE.md`, "How we work"). **No:** llaves de AWS guardadas en GitHub.
- **Sí:** bucket de estado creado a mano, una sola vez. **No:** un módulo `bootstrap` de Terraform con su propio estado local; para un bucket es más ceremonia que ayuda.
- **Sí:** copiar el histórico local a la nube con `pg_dump --data-only`. El trigger append-only solo bloquea `UPDATE`, `DELETE` y `TRUNCATE`, así que la carga con `INSERT` funciona. Perder dos días de histórico no tiene arreglo.
- **Sí:** alarma de errores y presupuesto desde el primer día. Si el scraper falla en silencio, el histórico se pierde sin que nadie lo note.
- **Sí:** objetos a Glacier Instant Retrieval a los 90 días. El HTML crudo solo se vuelve a leer para re-extraer y crece cada día.

## Riesgos identificados

| Riesgo | Mitigación |
| --- | --- |
| Londoño Gómez bloquea las IP de AWS | La primera corrida manual lo detecta. Plan B: correr el mismo contenedor como job programado de GitHub Actions o en Render, que ya estaba en el plan |
| El plan gratuito de Supabase pausa el proyecto tras 7 días sin actividad | La corrida diaria escribe en la base de datos; la alarma de errores avisa si la base deja de responder |
| La copia del histórico choca con filas ya creadas en la nube | Se copia antes de la primera corrida en la nube, con la base recién migrada y vacía |
| La imagen no corre en arm64 por una dependencia sin wheel | El build local del paso 6 lo detecta; se cambia a `x86_64` en una línea |
| `alembic check` en CI no ve la base en la nube | No hace falta: el CI sigue comparando contra Supabase local; la nube se migra con el mismo historial de Alembic |
| La primera corrida programada falla y no hay nadie mirando | Alarma por correo con `Errors >= 1` y la fila `failed` en `scrape_runs` |

## Lo que **no** entra en este spec

- SQS y varias constructoras.
- LocalStack, Infracost y `terraform plan` en los PR.
- `terraform apply` desde GitHub Actions.
- Despliegue de la API y ambientes separados.
- Playwright en Lambda.

Cada uno, si llega, va en su propio spec.
