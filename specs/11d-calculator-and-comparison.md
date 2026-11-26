# SPEC 11d — Calculadora, "¿Me alcanza?" y comparador

> **Estado:** aprobado
> **Depende de:** SPEC 08, SPEC 11b, SPEC 11c
> **Fecha:** 2026-11-25
> **Objetivo:** Agregar al sitio la calculadora "¿Qué puedo comprar?", el bloque "¿Me alcanza?" en cada ficha y el comparador de 2 a 4 proyectos por $/m², con la misma matemática de `finance.py` y una tasa de referencia de los bancos que la persona puede cambiar.

## Por qué existe este spec

La *Propuesta curada del frontend (SPEC 11)* ponía la calculadora, "¿Me alcanza?" y el comparador en el 11b, y el 11b los dejó fuera para no crecer demasiado (`specs/11b-search-and-map.md`, sección "Fuera"). Son las tres pantallas que convierten el precio "desde" en una decisión: cuánto puedo pagar, si este proyecto me alcanza y cuál sale más barato por metro cuadrado. Hoy esa matemática solo existe para el asesor (`src/sobreplano/domain/finance.py`).

Decisiones de Andrés del 25 nov que este spec aplica:

- Entran la calculadora, "¿Me alcanza?" y el comparador. Los favoritos van en otro spec.
- La tasa de interés viene llena con **el promedio vigente de los bancos que prestan para vivienda**, y la persona la puede cambiar.
- Los ingresos y el ahorro **se recuerdan siempre en este navegador**, con un botón para borrarlos. Nunca salen del dispositivo.
- Los proyectos para comparar se eligen **desde la búsqueda y desde la ficha**.

### De dónde sale la tasa de referencia

La Superintendencia Financiera publica en datos abiertos las tasas activas del formato 414, con las tasas efectivas anuales promedio ponderadas, los montos y el número de créditos desembolsados cada semana, por entidad y producto. El conjunto *Tasas de interés activas por tipo de crédito – Últimos dos meses* (`qzsc-9esp` en datos.gov.co) tiene licencia CC BY-SA 4.0, se actualiza cada semana (última carga: 20 nov 2026) y se consulta sin clave con la API SODA.

Consulta probada el 25 nov 2026: bancos (`tipo_entidad = '1'`), productos "Adquisición de vivienda vis (colocación en pesos)" y "Adquisición de vivienda no vis (colocación en pesos)", promedio de `tasa_efectiva_promedio` ponderado por `montos_desembolsados` en la semana más reciente.

| Corte | VIS | No VIS |
| --- | --- | --- |
| 13 nov 2026 | 14,57 % E.A. (1.153 créditos) | 15,45 % E.A. (737 créditos) |
| 6 nov 2026 | 14,52 % E.A. | 15,56 % E.A. |

Ponderar por monto hace que pesen más los bancos que más prestan, que es lo que Andrés pidió con "los bancos principales", sin mantener una lista de bancos a mano. Se excluyen los créditos en UVR, porque desde el 29 sep 2023 su tasa no incluye la variación de la UVR y no es comparable con una tasa en pesos.

### Estado actual del repo

`main` en `b280a37`, con el 11c ya integrado:

- `src/sobreplano/domain/finance.py:9-14`: tope de cuota del 40 % (Decreto 0583 de 2025), cuota inicial mínima del 20 % y por defecto del 30 %, tasa máxima del 40 % E.A., plazo de 5 a 30 años y hasta 60 meses de plan. `:96-126` `simulate_mortgage`, `:129-171` `max_affordable_price` y `:174-199` `down_payment_plan`, en `Decimal` con 50 dígitos y redondeo `ROUND_HALF_UP` a pesos.
- `src/sobreplano/interface/cli/export_openapi.py`: ya existe el patrón de un archivo generado desde Python con `--check` en CI.
- `src/sobreplano/interface/api/schemas.py:68-69`: la API trae `private_area_m2` y `built_area_m2` de cada tipología, pero `web/src/lib/projects.ts:20-22` las junta en un solo `areaM2` con su `areaBasis`. El comparador necesita las dos.
- `web/src/lib/search.ts:38`: la búsqueda ordena por precio, precio descendente, subida y nombre.
- `web/src/components/ProjectCard.tsx:1` y `:49`: la tarjeta L y la S del kit.
- `web/src/components/search/ResultCards.tsx:37`: la cuadrícula de la búsqueda pinta las tarjetas.
- `web/src/pages/proyectos/[slug].astro:64-101`: la ficha tiene tarjeta de precio, ficha técnica, histórico y tipologías.
- `web/src/components/SiteHeader.astro:20-27`: la navegación tiene "Proyectos" y "Asesor".
- `web/src/components/advisor/AdvisorPage.tsx:397-398`: ante el límite diario, el asesor solo ofrece "Seguir con la búsqueda".

## Alcance

**Dentro:**

- **Vectores compartidos:** un CLI de Python que corre `finance.py` sobre una lista fija de entradas y escribe las salidas en un JSON para las pruebas del sitio, con `--check` en CI.
- **Puerto a TypeScript** de `finance.py` (`web/src/lib/finance.ts`), con `decimal.js-light` para dar los mismos pesos que Python.
- **Tasa de referencia:** se lee de datos.gov.co al construir el sitio, con un respaldo versionado y su fecha, fuente y licencia a la vista.
- **`/calculadora/` "¿Qué puedo comprar?"**, con las tarjetas de formulario de *Tenancy Application* y las cifras de *Rental Portfolio* del kit:
  - ingreso mensual del hogar, ahorro para la cuota inicial, VIS o No VIS y meses hasta la entrega;
  - "Ajustes del crédito" plegado: tasa (llena con la de referencia), plazo y porcentaje de cuota inicial;
  - resultado: precio máximo, qué lo limita (ingreso o ahorro), cuota mensual, cuota frente al 30 % y al 40 % del ingreso, cuota inicial y cuánto al mes durante la obra;
  - botón "Ver N proyectos hasta $X", que abre la búsqueda con `precio_max`; si no hay ninguno, los tres más baratos con cuánto faltaría.
- **"¿Me alcanza?" en la ficha:** isla bajo la tarjeta de precio que, con los datos guardados, dice si el "desde" alcanza, cuánto faltaría y cuál sería la cuota. Sin datos guardados, pide ingreso y ahorro en el mismo bloque.
- **Comparador en `/comparar/?p=a,b,c`**, de 2 a 4 proyectos:
  - tabla con el estilo de la tabla de la ficha del kit: constructora y municipio, "desde" con su tipología y fecha, área y $/m² de cada tipología vigente, variación desde el primer precio, alcobas y baños y última observación;
  - selector "Área privada" o "Área construida", con "No reportada" cuando falta, sin estimarla;
  - la tipología con el menor $/m² de la tabla, marcada;
  - la fila "¿Me alcanza?" si hay datos guardados;
  - en móvil, dos proyectos lado a lado con un selector para cambiar cada columna.
- **Selección para comparar:** casilla "Comparar" en las tarjetas de la búsqueda con una barra flotante "Comparar (N)", y botón "Agregar al comparador" en la ficha. La selección vive en `localStorage` y la página la recibe en la URL.
- **Datos en el navegador:** las finanzas y la selección, cada una con su botón para borrarla.
- **Entradas:** "Calculadora" en la navegación, y los avisos de límite y presupuesto del asesor también ofrecen la calculadora.
- **Pruebas:** pytest del CLI de vectores; Vitest del puerto, la tasa, el almacenamiento y la URL del comparador; Playwright con axe, capturas y Lighthouse. Ninguna prueba sale a internet.
- **Documentación:** `docs/frontend.md`, `web/DESIGN.md`, `docs/security.md`, `docs/terms-of-use.md` y `CLAUDE.md`.

**Fuera (para specs futuros):**

- Favoritos (pantalla *Favorited Properties* del kit).
- Orden por $/m² en la búsqueda (ver Decisiones).
- Créditos en UVR, leasing habitacional, subsidios (Mi Casa Ya, cajas de compensación), seguros y gastos de escrituración y registro: el cierre financiero completo (SPEC 13).
- Tasa de referencia en el asesor. El SPEC 08 decidió que el asesor pregunta la tasa; cambiarlo mueve las evals.
- Clasificación VIS de cada proyecto y fecha de entrega: la API no las tiene (SPEC 16). La persona elige VIS o No VIS y escribe los meses.
- Gráfica de amortización y comparar más de 4 proyectos.

## Modelo de datos

La API y la base de datos no cambian.

### 1. Vectores compartidos

`src/sobreplano/interface/cli/finance_vectors.py` escribe `web/tests/fixtures/finance-vectors.json`:

```json
{
  "constants": { "maxPaymentToIncome": "0.40", "minDownPaymentPct": "20", "maxRateEaPct": "40",
                 "minYears": 5, "maxYears": 30, "maxPlanMonths": 60 },
  "mortgage":   [{ "input": { "priceCop": 289900000, "rateEaPct": "15.45", "years": 20,
                              "downPaymentPct": "30" },
                   "output": { "monthlyPaymentCop": 0, "...": "todos los campos de MortgageSimulation" } }],
  "affordability": [{ "input": { "...": "..." }, "output": { "...": "..." } }],
  "downPaymentPlan": [{ "input": { "...": "..." }, "output": { "...": "..." } }],
  "errors": [{ "fn": "simulate_mortgage", "input": { "years": 4 }, "message": "years must be between 5 and 30" }]
}
```

- Al menos 20 casos por función: bordes (20 % y 99 % de cuota inicial, 5 y 30 años, 1 y 60 meses, tasa de 0,01 % y 40 %), precios del catálogo, ahorro 0, ingreso que limita y ahorro que limita, y un caso que cae justo en ,5 al redondear.
- Los errores se comparan por tipo de regla, no por texto: el sitio muestra sus propios textos en español.
- `--check` sale con 1 si el archivo difiere de lo que produce `finance.py`.

### 2. Puerto (`web/src/lib/finance.ts`)

Mismas tres funciones y constantes, con los mismos nombres en camelCase. Usa `decimal.js-light` con 50 dígitos y `ROUND_HALF_UP`, y devuelve enteros en pesos. Lanza `FinanceInputError` con un código (`rate-out-of-range`, `years-out-of-range`, …) que la interfaz traduce. Si el JSON de vectores dice un número, el puerto da ese mismo número.

### 3. Tasa de referencia

`web/src/data/reference-rate.json`, versionado:

```json
{
  "vis":    { "rateEaPct": 14.57, "loans": 1153 },
  "noVis":  { "rateEaPct": 15.45, "loans": 737 },
  "cutOff": "2026-11-13",
  "fetchedOn": "2026-11-25",
  "source": "Superintendencia Financiera de Colombia, datos abiertos (formato 414), CC BY-SA 4.0",
  "sourceUrl": "https://www.datos.gov.co/d/qzsc-9esp"
}
```

- `web/src/lib/reference-rate.ts` lo usa así:
  - En el build, si `REFERENCE_RATE=live`, consulta la API SODA de `qzsc-9esp` con la consulta de arriba y usa el resultado.
  - Si falla la red o la respuesta no pasa la validación, usa el archivo versionado y lo anota en el log del build.
  - En CI y en las pruebas (`REFERENCE_RATE` sin definir), usa siempre el archivo, para que las capturas no cambien.
- **Validación:** cada tasa entre 5 % y 30 % E.A., al menos 50 créditos en la semana y corte de menos de 45 días. Si una tasa no cumple, se usa la del archivo.
- `pnpm --dir web rate:update` reescribe el archivo con la consulta en vivo, para actualizar el respaldo en un PR.
- La tasa se redondea a dos decimales y se muestra así: "Tasa promedio de los bancos para vivienda No VIS: 15,45 % E.A., semana del 13 nov 2026. Fuente: Superfinanciera (datos abiertos)."
- La reconstrucción diaria del sitio (SPEC 12) la mantiene al día. Hasta entonces se actualiza con `rate:update`.

### 4. Datos en el navegador

```ts
// clave "sobreplano.finanzas.v1"
type StoredFinances = {
  incomeCop: number | null;
  savingsCop: number | null;
  housing: "vis" | "no-vis";          // No VIS por defecto
  monthsToDelivery: number | null;
  rate: { source: "reference" } | { source: "custom"; eaPct: number };
  years: number;                      // 20 por defecto
  downPaymentPct: number;             // 30 por defecto
  updatedAt: string;
};

// clave "sobreplano.comparar.v1"
type StoredComparison = { slugs: string[] };   // de 0 a 4, sin repetidos
```

- Con `rate.source = "reference"`, la tasa sigue a la del build. Si la persona la cambia, queda `custom` hasta que toque "Usar la tasa de referencia".
- **"Olvidar mis datos"** borra `sobreplano.finanzas.v1`. **"Quitar todos"** vacía la selección del comparador.
- Sin `localStorage` (modo privado o cuota llena), todo funciona en memoria y lo dice.
- Ingresos y ahorro nunca van en la URL ni en una petición. A la búsqueda solo viaja `precio_max`.

### 5. URL

| Página | Parámetro | Regla |
| --- | --- | --- |
| `/comparar/` | `p=slug-a,slug-b` | De 2 a 4 slugs del catálogo del build. Los desconocidos y repetidos se ignoran. Con menos de 2 válidos, la página explica cómo elegir y enlaza a la búsqueda |
| `/proyectos/` | `precio_max` | Ya existe (11b). La calculadora lo usa |

Abrir `/comparar/?p=…` reemplaza la selección guardada por la de la URL, para que un enlace compartido muestre lo mismo a cualquiera.

### 6. Reglas de la calculadora

- **Precio máximo:** `maxAffordablePrice(ingreso, ahorro, tasa, plazo, % cuota inicial)`, el menor entre el límite por ingreso y el límite por ahorro, con la frase de cuál limita.
- **Cuota:** la del precio máximo (`simulateMortgage`), con dos marcas: "Hasta 30 % de tu ingreso: holgado" y "Hasta 40 %: el máximo que permite la ley". La de 30 % es una guía, no una regla del banco.
- **Durante la obra:** con meses hasta la entrega, `downPaymentPlan(precio máximo, % cuota inicial, meses, ahorro)` da cuánto pagar al mes. El ahorro cuenta como abono inicial hasta el valor de la cuota inicial.
- **"¿Me alcanza?" en la ficha:** con el "desde" del proyecto:
  - si el precio es menor o igual al máximo: "Te alcanza", con la cuota y su porcentaje del ingreso;
  - si lo limita el ahorro: "Te faltan $X de cuota inicial", con el plan mensual si hay meses;
  - si lo limita el ingreso: "La cuota sería $Y, el Z % de tu ingreso; el máximo es 40 %";
  - siempre dice para qué tipología y con qué tasa se calculó.
- **Supuestos visibles** en las tres pantallas: tasa fija en pesos, sin seguros ni gastos de escrituración, no es una oferta ni una preaprobación.

## Plan de implementación

1. **Vectores.** `finance_vectors.py` con su docstring, el JSON generado y `tests/unit/interface/test_finance_vectors.py`, que falla si el archivo está desactualizado. La regla en CI, junto a `export_openapi --check`. Commit `feat:`.
2. **Puerto.** `web/src/lib/finance.ts` y `web/tests/unit/finance.test.ts`, que recorre todos los vectores y los errores. Dependencia `decimal.js-light`. Commit `feat:`.
3. **Tasa de referencia.** `web/src/data/reference-rate.json` con el corte del 13 nov 2026, `reference-rate.ts`, el script `rate:update` y sus tests: respuesta válida, red caída, tasa fuera de rango, pocos créditos, corte viejo y la variable sin definir. Commit `feat:`.
4. **Datos del navegador y vista.** `privateAreaM2` y `builtAreaM2` en `UnitTypeView` (`projects.ts`), `web/src/lib/finances-store.ts` y `web/src/lib/compare-store.ts`, con sus tests (lectura de versiones viejas, cuota llena, modo en memoria, máximo 4 en la selección). Commit `feat:`.
5. **Calculadora.** `web/src/pages/calculadora/index.astro` con la isla `Calculator` (`client:load`): campos con `inputMode="numeric"` y miles con punto al salir del campo, etiquetas siempre visibles, errores junto a cada campo, resultado en `role="status"` y el enlace a la búsqueda. Commit `feat:`.
6. **"¿Me alcanza?"** en `web/src/components/finance/AffordabilityBlock.tsx`, montado en la ficha con `client:visible` debajo de `PriceCard`. Commit `feat:`.
7. **Comparador.**
   - La casilla "Comparar" en `ProjectCard` (solo en la búsqueda) y la barra flotante "Comparar (N)" con "Ver comparación" y "Quitar todos" en `SearchPage`.
   - El botón "Agregar al comparador" en la ficha.
   - `web/src/pages/comparar/index.astro` con la isla `Comparison`, que recibe los `SearchItem` del catálogo y las áreas de cada tipología.
   - `<table>` con `scope` en las cabeceras, $/m² en `tabular-nums`, la marca del menor $/m² con texto (no solo color) y la vista móvil de dos columnas.

   Commit `feat:`.
8. **Entradas.** "Calculadora" en `SiteHeader.astro` (escritorio y menú móvil). En `AdvisorPage.tsx`, el aviso de límite diario y el de presupuesto suman "Probar la calculadora". Las capturas que cambian se regeneran en Linux. Commit `feat:`.
9. **Pruebas de navegador.**
   - Playwright: calculadora completa y su enlace a `/proyectos/?precio_max=…`; el resultado sin proyectos; recargar y ver los datos guardados; "Olvidar mis datos"; tasa propia y volver a la de referencia; "¿Me alcanza?" en sus tres casos; elegir dos proyectos en la búsqueda y uno en la ficha y comparar los tres; el cambio de área privada a construida con "No reportada"; un enlace compartido que reemplaza la selección; menos de 2 proyectos válidos; móvil con dos columnas.
   - axe en `/calculadora/`, `/comparar/` y la ficha con el bloque, a 390 y 1440 px.
   - Capturas a 390 y 1440 px de las dos páginas nuevas.
   - Lighthouse en las dos páginas nuevas.

   Commit `test:`.
10. **Documentación.**
    - `docs/frontend.md`: las páginas, el almacenamiento, la tasa de referencia y cómo actualizarla.
    - `web/DESIGN.md`: el formulario, las cifras del resultado y la tabla del comparador.
    - `docs/security.md`: datos.gov.co como fuente leída en el build y los datos financieros que se quedan en el navegador.
    - `docs/terms-of-use.md`, en los dos idiomas: la tasa es un promedio de referencia, y los ingresos y el ahorro se guardan solo en el navegador.
    - `CLAUDE.md`: el comando del CLI de vectores y la línea de estado.

    Commit `docs:`.

Ningún paso tiene llamadas pagas ni cuentas nuevas. En `web/` entra `decimal.js-light`; en Python no entra nada.

## Criterios de aceptación

Cada criterio se verifica pegando el comando y su salida en el PR (constitución, principio 6).

- [ ] `uv run python -m sobreplano.interface.cli.finance_vectors --check` sale con 0, y sale con 1 al cambiar un caso del JSON (probado y revertido).
- [ ] `uv run pytest -m "not integration"`, `uv run ruff check`, `uv run ruff format --check`, `uv run pyright` y `uv run lint-imports` pasan.
- [ ] `pnpm --dir web test` pasa, incluido `finance.test.ts`, que recorre todos los vectores y da los mismos pesos que Python en cada caso.
- [ ] `pnpm --dir web check`, `pnpm --dir web rules` y `pnpm --dir web tokens && git diff --exit-code web/src/styles/tokens.css` pasan.
- [ ] `REFERENCE_RATE=live pnpm --dir web rate:update` escribe un corte de los últimos 45 días con dos tasas entre 5 % y 30 %. El PR pega la salida.
- [ ] Sin red y con `REFERENCE_RATE=live`, `pnpm --dir web build` termina, usa el archivo versionado y lo anota en el log.
- [ ] En `/calculadora/`, con ingreso de $8.000.000, ahorro de $60.000.000, No VIS, 20 años y 30 %, el precio máximo, la cuota y lo que limita coinciden con `max_affordable_price` de Python para la tasa de referencia del archivo (Playwright compara contra un vector).
- [ ] "Ver N proyectos hasta $X" abre `/proyectos/?precio_max=X` y la búsqueda muestra esos N proyectos.
- [ ] Ninguna petición del navegador lleva el ingreso ni el ahorro: Playwright revisa las URL y los cuerpos de todas las peticiones de la sesión.
- [ ] Al recargar la página, los datos siguen ahí. "Olvidar mis datos" los borra y el formulario queda vacío.
- [ ] Con una tasa propia, el resultado la usa. "Usar la tasa de referencia" vuelve a la del build.
- [ ] En una ficha, con datos guardados, "¿Me alcanza?" muestra el caso correcto (alcanza, falta ahorro, cuota alta) para tres proyectos del catálogo ficticio elegidos para cada caso.
- [ ] Al elegir dos proyectos en la búsqueda y uno desde una ficha, "Comparar (3)" abre `/comparar/?p=…` con los tres en ese orden.
- [ ] Con "Área construida", una tipología sin área construida dice "No reportada" y no entra en la marca del menor $/m².
- [ ] `/comparar/?p=uno,inexistente,uno` muestra la explicación de menos de 2 proyectos y el enlace a la búsqueda.
- [ ] `@axe-core/playwright` no reporta violaciones en `/calculadora/`, `/comparar/` y la ficha con el bloque, a 390 y 1440 px.
- [ ] A 320 px de ancho, ninguna de las páginas nuevas tiene scroll horizontal.
- [ ] Lighthouse CI (móvil) en `/calculadora/` y `/comparar/`: rendimiento ≥ 0,90, accesibilidad = 1,00 y CLS ≤ 0,1. El PR anota el JavaScript inicial de cada una (gzip), que debe ser ≤ 90 KB.
- [ ] La CSP no cambia y no hay mensajes `Content Security Policy` en la consola.
- [ ] La fuente, la licencia y la fecha de corte de la tasa se ven en la calculadora y en "¿Me alcanza?".
- [ ] Las capturas de las páginas nuevas están aprobadas y el PR las muestra al lado de *Tenancy Application* y *Rental Portfolio* del kit. Las de la navegación que cambian se regeneran en Linux.
- [ ] `grep -rl '"history"' web/dist` no devuelve nada.
- [ ] Los workflows `ci.yml` y `web.yml` quedan en verde en el PR.

## Decisiones tomadas y descartadas

- **Sí:** calculadora, "¿Me alcanza?" y comparador en un spec (Andrés, 25 nov). Comparten el catálogo del build, el almacenamiento del navegador y, las dos primeras, la matemática. **No:** favoritos aquí.
- **Sí:** tasa llena con el promedio de los bancos y editable (Andrés, 25 nov), leída de los datos abiertos de la Superfinanciera. **No:** una tasa escrita a mano, que envejece sin que nadie lo note, ni bajar las tasas desde el navegador, que pondría un tercero en la CSP y en la privacidad de cada visita.
- **Sí:** promedio ponderado por monto desembolsado de todos los bancos. **No:** una lista fija de "bancos principales", que habría que mantener y que no dice nada que el monto no diga ya.
- **Sí:** tasas en pesos. **No:** UVR, cuya tasa no incluye la variación de la UVR desde el 29 sep 2023 y daría una cuota engañosamente baja.
- **Sí:** VIS o No VIS lo elige la persona, con No VIS por defecto. La API no sabe si un proyecto es VIS (SPEC 16), y el precio solo no basta para clasificarlo.
- **Sí:** finanzas guardadas siempre en `localStorage` (Andrés, 25 nov), con "Olvidar mis datos". **No:** guardarlas en la URL, que se comparte y queda en el historial.
- **Sí:** puerto a TypeScript con vectores generados desde Python y `decimal.js-light`. **No:** números de punto flotante, que pueden cambiar un peso al redondear y harían que la calculadora y el asesor den cifras distintas. **No:** llamar al asesor o a un endpoint nuevo para calcular, porque los ingresos saldrían del dispositivo.
- **Sí:** una sola página para la calculadora, con las tarjetas de formulario del kit y los ajustes plegados. **No:** el paso a paso de *Tenancy Application*: son seis campos, y partirlos en pasos esconde el resultado.
- **Sí:** selección del comparador desde la búsqueda y la ficha, guardada en `localStorage` y pasada en la URL (Andrés, 25 nov). La URL manda al abrir, para que un enlace compartido muestre lo mismo.
- **Sí:** $/m² siempre sobre un área elegida, privada o construida, con "No reportada" cuando falta. **No:** mezclar bases en una misma columna (regla de la *Propuesta curada*, Gráficas).
- **No:** orden por $/m² en la búsqueda. Cada tarjeta muestra el "desde" sobre su propia área, privada o construida, y ordenarlas juntas mezclaría bases. El comparador resuelve esa pregunta con la base elegida.
- **No:** gastos de escrituración y seguros en la cuota. Las fuentes no coinciden en cuánto suman (*Propuesta curada*, §5), así que van en el SPEC 13 con su cifra verificada. Mientras tanto, la calculadora dice que no los incluye.

## Riesgos identificados

| Riesgo | Mitigación |
| --- | --- |
| datos.gov.co cambia el nombre de una columna, del conjunto o de los productos | Validación de la respuesta y respaldo versionado con su fecha. `rate:update` falla con el motivo, y la fecha de corte vieja se ve en la página |
| La API SODA no responde durante el build | El build usa el respaldo y sigue |
| La tasa de referencia se lee como la tasa que le darán a la persona | Texto junto al campo: "Es un promedio de lo que prestaron los bancos esa semana. Tu banco puede darte otra". El campo se puede cambiar |
| Un comprador VIS ve la tasa No VIS por defecto | El selector VIS o No VIS está junto a la tasa, y el resultado dice con cuál se calculó |
| Ingresos guardados en un computador compartido | "Olvidar mis datos" siempre visible y el aviso de que se guardan en este navegador |
| El puerto se desvía de Python en un cambio futuro de `finance.py` | El `--check` de los vectores en CI lo detecta en el mismo PR |
| Pocos proyectos con área privada hacen que el comparador muestre mucho "No reportada" | El selector deja pasar a área construida. Antes de implementar, una consulta a la base dice la proporción real, y el PR la anota |
| Licencia CC BY-SA de los datos | Atribución visible con la licencia y el enlace al conjunto. El sitio solo muestra un promedio, no redistribuye el conjunto |

## Lo que **no** entra en este spec

- Favoritos.
- Orden por $/m² en la búsqueda.
- UVR, leasing, subsidios, seguros y gastos de cierre (SPEC 13).
- Tasa de referencia en el asesor.
- Clasificación VIS y fecha de entrega de cada proyecto (SPEC 16).
- Gráfica de amortización y comparar más de 4 proyectos.

Cada uno, si llega, va en su propio spec.
