# SPEC 11b — Búsqueda con filtros y mapa

> **Estado:** implementado
> **Depende de:** SPEC 11a
> **Fecha:** 2026-11-25
> **Objetivo:** Convertir `/proyectos/` en una búsqueda con filtros guardados en la URL y un mapa de OpenFreeMap con píldoras de precio, calcada de la pantalla *Search Result (Map v2)* del kit Estatery.

## Por qué existe este spec

El listado del 11a muestra todos los proyectos en una cuadrícula sin filtros (`web/src/pages/proyectos/index.astro:1-3` lo deja para este spec). Quien busca vivienda llega con un municipio, un presupuesto y un número de alcobas. Sin filtros ni mapa tiene que recorrer todas las tarjetas.

Este spec se escribió de noche, sin la ronda de preguntas de `/spec`, porque Andrés pidió dejarlo listo mientras dormía. Cada decisión que habría ido a una pregunta está marcada en **Decisiones** con "(sin confirmar)". Andrés las revisa antes de aprobar.

Fuentes:

- Pantallas del kit: *Search Result (Map v2)* (lista más mapa, píldoras, chips, orden), *Search Result - Filter (Map v2)* (panel "Más filtros" con histograma de precio) y, en móvil, *Search Result (Swipe Up)* y *Search Map v2* (botón "Open Maps" y mapa a pantalla completa con contador).
- *Decisiones de diseño del frontend (SPEC 11)*, sección "Vista de mapa estilo Airbnb".
- Cuaderno C3-P1 (búsqueda y ficha): filtros en la URL, chips activos con "X", conteo vivo, estado de cero resultados, lista más mapa, proyectos sin coordenadas.
- Cuaderno C4-P1 (mapa con presupuesto cero): MapLibre GL JS sobre OpenFreeMap, agrupación con Supercluster, atribución visible, PMTiles en R2 como respaldo.
- Cuaderno C4-P3 (accesibilidad de mapa y gráficas): la lista es la alternativa accesible del mapa; conteo anunciado con `aria-live`.

Estado actual del repo (`main` en `6221546`):

- `web/src/lib/catalog.ts:19-34`: el build ya trae todo el catálogo con `GET /projects`, de 50 en 50. `:45-53`: `sortByFrom` ordena por "desde".
- `web/src/lib/projects.ts:15-49`: `UnitTypeView` y `ProjectView` ya traen lo que la búsqueda necesita: municipio, barrio, `location` (nula si la constructora no publica mapa), alcobas, baños, área con su base, precio vigente, variación y estado de cada tipología.
- `web/src/components/ProjectCard.astro:1-30`: la tarjeta L del kit es un componente Astro. Una isla de React no puede usarlo.
- `web/astro.config.mjs:27-37`: la CSP solo permite `'self'` y el origen de la API. Un mapa de OpenFreeMap necesita más.
- `src/sobreplano/interface/api/routes/projects.py:35-36`: la API pagina de 50 en 50 y filtra por municipio, constructora, precio, alcobas y área, pero este spec no la llama desde el navegador (ver Decisiones).
- `src/sobreplano/interface/api/schemas.py:116-126`: un proyecto no trae fecha de entrega ni clasificación VIS (`docs/schema.md:132` las deja para otro spec). Por eso no hay filtros por entrega ni por VIS.

## Alcance

**Dentro:**

- **Búsqueda en `/proyectos/`** como isla de React (`client:load`), con el HTML completo del listado generado en el build, para que la página funcione y se indexe sin JavaScript.
- **Filtros, todos en la URL:**
  - texto libre (nombre del proyecto, barrio, municipio o constructora, sin importar tildes ni mayúsculas);
  - municipios (varios);
  - constructora;
  - rango de precio con histograma;
  - alcobas mínimas y baños mínimos;
  - rango de área;
  - orden: precio de menor a mayor (por defecto), de mayor a menor, mayor subida y nombre.
- **Filtros como en el kit:**
  - fila de filtros rápidos (Precio, Alcobas, Municipio y orden), cada uno en un popover que aplica al instante;
  - botón "Más filtros", que abre el panel lateral del kit con todos los filtros, conteo vivo y los botones "Limpiar" y "Ver N proyectos";
  - chips de los filtros activos con su "X" y "Limpiar todo".
- **Tarjeta honesta con filtros:** si hay filtros por tipología, la tarjeta muestra como "desde" la tipología más barata que cumple todos los filtros, con su nombre, su fecha y su variación.
- **Mapa en escritorio (≥ 1024 px)**, a la izquierda y a media pantalla, como en el kit:
  - MapLibre GL JS con el estilo Positron de OpenFreeMap, repintado con los tokens de mapa;
  - píldoras con precio y variación ("$289 M +9,8 %");
  - agrupación de píldoras cercanas;
  - tarjeta flotante al seleccionar una píldora;
  - resaltado mutuo entre tarjeta y píldora al pasar el puntero o el foco;
  - "Buscar al mover el mapa", activado por defecto;
  - contador "N proyectos en esta zona del mapa";
  - zoom con botones y con la rueda;
  - atribución de OpenFreeMap, OpenMapTiles y OpenStreetMap siempre visible.
- **Proyectos sin coordenadas:** nunca desaparecen. Con el filtro del mapa activo, van al final de la lista en el grupo "Sin ubicación publicada (N)".
- **Móvil y tablet (< 1024 px):**
  - la lista por defecto, con el botón oscuro flotante "Ver mapa" del kit;
  - el mapa a pantalla completa, con la barra inferior "N proyectos en esta zona" y el botón "Ver lista";
  - el botón "Atrás" del navegador vuelve del mapa a la lista.
- **Buscador del hero del inicio:** el que el 11a dejó para este spec. Es un formulario sin JavaScript (`GET /proyectos/`) con municipio y presupuesto máximo.
- **CSP** ampliada solo con lo que el mapa necesita.
- **Catálogo ficticio:** dos proyectos nuevos a menos de 300 m entre sí, para probar la agrupación. Para las pruebas, un estilo de mapa local sin red.
- **Pruebas:** Vitest para toda la lógica de búsqueda; Playwright con axe, capturas y Lighthouse.
- **Documentación:** `docs/frontend.md`, `web/DESIGN.md`, `docs/security.md`, `docs/terms-of-use.md` y `CLAUDE.md`.

**Fuera (para specs futuros):**

- Dibujar una zona a mano alzada en el mapa (terra-draw), aunque *Decisiones de diseño* lo ponía en el 11b.
- Comparador por $/m², calculadoras ("¿Qué puedo comprar?", cuota inicial) y favoritos.
- Hoja inferior con tres anclajes en móvil (patrón de Airbnb). Aquí el móvil alterna entre lista y mapa, como en el kit.
- Vista de lista horizontal (*Search (Map v1)*) y botón para cambiar entre cuadrícula y lista.
- Filtros por fecha de entrega, VIS o subsidio: la API no tiene esos datos.
- Capas de puntos de interés (Metro, colegios), edificios en 3D, vista satelital y "mi ubicación".
- Teselas propias (PMTiles del Valle de Aburrá en R2): queda documentado como plan B, sin implementarlo.
- Asesor en la web (11c) y despliegue (SPEC 12).

## Modelo de datos

La API y la base de datos no cambian. Todo se calcula en el navegador sobre el catálogo que el build ya tiene.

### 1. Índice de búsqueda (`web/src/lib/search.ts`)

El build convierte cada `ProjectView` en un `SearchItem`. La isla lo recibe como propiedad. Solo lleva datos que ya están en el HTML de las tarjetas, nunca el histórico.

```ts
type SearchUnit = {
  name: string;
  bedrooms: number | null;
  bathrooms: number | null;
  areaM2: number;
  areaBasis: "private" | "built";
  priceCop: number;          // solo tipologías vigentes (status "current")
  changePct: number | null;
};

type SearchItem = {
  slug: string;
  name: string;
  developer: { name: string; slug: string };
  municipality: Municipality;
  neighborhood: string | null;
  location: { lat: number; lon: number } | null;
  lastObservedOn: string | null;
  units: SearchUnit[];       // vigentes, de la más barata a la más cara
  searchText: string;        // nombre, barrio, municipio y constructora, en minúsculas y sin tildes
};
```

Un proyecto sin tipologías vigentes tiene `units: []` y su tarjeta dice "Sin precio publicado", como en el 11a.

### 2. Estado de la búsqueda y su URL

```ts
type SearchState = {
  q: string;
  municipalities: Municipality[];
  developer: string | null;
  priceMin: number | null; priceMax: number | null;   // COP
  bedroomsMin: number | null; bathroomsMin: number | null;
  areaMin: number | null; areaMax: number | null;     // m²
  sort: "precio" | "precio_desc" | "subida" | "nombre";
  map: { lat: number; lon: number; zoom: number } | null;
  searchOnMove: boolean;
  view: "lista" | "mapa";                             // solo cuenta por debajo de 1024 px
};
```

| Parámetro | Ejemplo | Regla |
| --- | --- | --- |
| `q` | `q=ditaires` | Texto libre, hasta 80 caracteres |
| `municipio` | `municipio=itagui,envigado` | Slugs de `Municipality`, separados por coma |
| `constructora` | `constructora=constructora-ejemplo` | Slug de la constructora |
| `precio_min`, `precio_max` | `precio_max=400000000` | Pesos, enteros |
| `alcobas`, `banos` | `alcobas=2` | Mínimos, de 1 a 5 |
| `area_min`, `area_max` | `area_min=50` | m² enteros |
| `orden` | `orden=subida` | `precio` (por defecto), `precio_desc`, `subida`, `nombre` |
| `mapa` | `mapa=6.1725,-75.6130,12.5` | Latitud y longitud con 4 decimales, zoom con 1 |
| `mover` | `mover=0` | Solo aparece cuando "Buscar al mover el mapa" está apagado |
| `vista` | `vista=mapa` | Solo aparece en la vista de mapa por debajo de 1024 px |

- `parseSearch(params)` nunca lanza un error. Un valor inválido o desconocido se ignora y desaparece de la URL en la siguiente escritura.
- `serializeSearch(state)` escribe los parámetros siempre en el orden de la tabla y omite los valores por defecto. Así, una misma búsqueda siempre produce la misma URL.
- **Escritura en el historial:**
  - un cambio de filtro u orden usa `history.replaceState`, así que "Atrás" sale de la búsqueda hacia la página anterior;
  - mover el mapa también usa `replaceState`, con una espera de 250 ms;
  - pasar a la vista de mapa en móvil usa `history.pushState`, así que "Atrás" vuelve a la lista;
  - al volver desde una ficha, la URL trae la búsqueda completa.

### 3. Reglas de coincidencia y orden

- **Filtros de proyecto:** texto, municipio y constructora.
- **Filtros de tipología:** precio, alcobas, baños y área. Una tipología cumple si satisface todos a la vez; un proyecto cumple si tiene al menos una tipología que los cumpla. Si no hay filtros de tipología, cumple todo proyecto, con precio o sin él.
- **"Desde" con filtros:** la tipología más barata entre las que cumplen. La tarjeta y la píldora muestran ese precio, su variación, su nombre y su área.
- **Orden:**
  - `precio` y `precio_desc` usan el "desde" con filtros, y los proyectos sin precio van al final;
  - `subida` ordena por la variación de esa tipología, de mayor a menor, y deja al final los que no tienen variación;
  - `nombre` ordena por nombre en `es-CO`, con números naturales;
  - los empates se resuelven por nombre.
- **Filtro del mapa:** solo aplica en escritorio, con el mapa visible y "Buscar al mover el mapa" encendido. Deja los proyectos con `location` dentro de los límites visibles. Los que no tienen coordenadas pasan al grupo "Sin ubicación publicada".
- **Histograma de precio:** 24 barras con el "desde" de los proyectos que cumplen los demás filtros. Sus extremos son el precio mínimo y el máximo del catálogo, redondeados al millón.

### 4. Píldora del mapa

- **Texto:** `formatMillions(precio)` del "desde" con filtros, más la variación si existe ("+9,8 %"). Sin precio, la píldora dice "Sin precio".
- **Nombre accesible:** "{nombre}, desde {precio en pesos}, subió {x} %".
- **Estilos del kit:**
  - normal: blanca con texto `#100A55`;
  - con el puntero o el foco: borde `action.default`;
  - seleccionada: fondo `action.default` y texto blanco.
- **Grupos:** un círculo con el número de proyectos. Al hacer clic, el mapa se acerca hasta separarlos.

## Plan de implementación

1. **Lógica de búsqueda.** `web/src/lib/search.ts` con `toSearchItem`, `parseSearch`, `serializeSearch`, `matchProject` (devuelve las tipologías que cumplen), `searchResults` (filtra, elige el "desde" y ordena), `inBounds`, `priceHistogram` y `normalizeText`. Sus tests en `web/tests/unit/search.test.ts`: ida y vuelta de la URL, valores inválidos, todos los filtros de tipología sobre la misma tipología, los cuatro órdenes con empates, proyectos sin precio y sin coordenadas, y búsqueda sin tildes. Commit `feat:`.
2. **Tarjeta en React.**
   - `ProjectCard.astro` pasa a `web/src/components/ProjectCard.tsx`, con la misma marca y las mismas clases. Recibe la tipología del "desde" como propiedad opcional.
   - Lo mismo `Icon.astro`, que pasa a `Icon.tsx` con los SVG de `web/src/lib/icons.ts` en el build, y `PriceChangeBadge`.
   - Las páginas del 11a los usan sin hidratar: sin `client:*`, así que no envían JavaScript.
   - Las capturas del 11a no cambian.

   Commit `refactor:`.
3. **Isla de búsqueda sin mapa.**
   - `web/src/components/search/SearchPage.tsx` lleva la cabecera "N proyectos", el buscador, los filtros rápidos, "Más filtros", los chips, el orden, la cuadrícula, el estado de cero resultados y la sincronía con la URL.
   - Componentes de shadcn sobre Radix: `popover`, `sheet`, `slider`, `checkbox` y `select`, revisados contra los tokens como en el 11a.
   - `/proyectos/` monta la isla con los `SearchItem` como propiedad.
   - Para que no parpadee la lista sin filtros, un `<script is:inline>` en el `<head>` marca el documento cuando la URL trae filtros. Mientras tanto, la cuadrícula muestra esqueletos del mismo tamaño hasta que la isla hidrata.

   Commit `feat:`.
4. **Buscador del hero.** En `web/src/pages/index.astro` va el buscador del kit en el lugar del botón "Ver proyectos". Es un `<form method="get" action="/proyectos/">` con dos selectores: "Municipio" (los municipios que tienen proyectos) y "Presupuesto" (hasta $250, $300, $400, $500 o $700 millones, o "Sin tope"). Lleva el botón "Ver proyectos" y no usa JavaScript. Commit `feat:`.
5. **Mapa.**
   - `web/src/components/search/ResultsMap.tsx` se carga con `import()` solo cuando el mapa se va a ver.
   - Usa `maplibre-gl` 6, con `setWorkerUrl` y el worker servido desde el sitio, el estilo `https://tiles.openfreemap.org/styles/positron` y las capas de tierra, parques y agua repintadas con los tokens `map.*`.
   - Las píldoras son marcadores HTML (`<button>`), agrupados con `supercluster`.
   - Implementa la tarjeta flotante (Esc la cierra), el resaltado mutuo, el "Buscar al mover el mapa" con espera de 250 ms, el encuadre inicial con todos los proyectos con coordenadas (o el parámetro `mapa`), el contador con `aria-live="polite"` y el enlace "Saltar el mapa".
   - Si el estilo o las teselas fallan, o no hay WebGL, el panel muestra "No pudimos cargar el mapa. La lista sigue funcionando." y la lista deja de filtrar por zona.
   - La CSP suma `https://tiles.openfreemap.org` a `connect-src`, `blob:` a `img-src` y `worker-src 'self'`. Si MapLibre necesita `blob:` en `worker-src`, se agrega y se anota por qué en `docs/security.md`.

   Commit `feat:`.
6. **Móvil.** Por debajo de 1024 px, la vista de lista lleva el botón flotante "Ver mapa" del kit (oscuro, con el icono `map-outline`). La vista de mapa ocupa la pantalla bajo la navegación, con la barra inferior "N proyectos en esta zona" y el botón "Ver lista". Al tocar una píldora, la tarjeta aparece abajo. El estado `vista=mapa` va en la URL con `pushState`. Commit `feat:`.
7. **Datos de prueba.** En `web/tests/fixtures/catalog.json`, dos proyectos ficticios a menos de 300 m entre sí. En `web/tests/fixtures/map-style.json`, un estilo de MapLibre con solo un fondo y sin fuentes ni teselas externas. Playwright redirige con `page.route` las peticiones a `tiles.openfreemap.org` hacia ese estilo, así que las pruebas no dependen de la red. Las capturas del 11a que cambian por los dos proyectos nuevos se regeneran en Linux. Commit `test:`.
8. **Pruebas de navegador.**
   - Playwright cubre: filtros desde la URL; los cambios de filtro que reescriben la URL; ir a la ficha y volver sin perder los filtros; cero resultados y "Limpiar todo"; las píldoras con su contador; la tarjeta flotante; el resaltado mutuo; mover el mapa con el teclado y ver cambiar el contador; los grupos; el mapa caído; móvil con "Ver mapa" y "Atrás"; y la página sin JavaScript.
   - axe revisa la búsqueda con el panel "Más filtros" abierto y la vista de mapa.
   - Hay capturas a 390 y 1440 px.
   - Lighthouse corre sobre `/proyectos/`.

   Commit `test:`.
9. **Documentación.**
   - `docs/frontend.md`: la búsqueda, los parámetros de la URL, el mapa, cómo se prueba sin red y el plan B con PMTiles en R2.
   - `web/DESIGN.md`: la píldora, el grupo, la tarjeta flotante y el botón "Ver mapa".
   - `docs/security.md`: la CSP nueva y OpenFreeMap como tercero que recibe la IP y la zona que mira el visitante.
   - `docs/terms-of-use.md`: una línea que dice que el mapa viene de OpenFreeMap y OpenStreetMap.
   - `CLAUDE.md`: la línea de estado.

   Commit `docs:`.

Ningún paso tiene llamadas pagas ni cuentas nuevas.

## Criterios de aceptación

Cada criterio se verifica pegando el comando y su salida en el PR (constitución, principio 6).

- [x] `pnpm --dir web test` pasa, incluido `search.test.ts`, que cubre como mínimo los casos del paso 1.
- [x] `pnpm --dir web check`, `pnpm --dir web rules` y `pnpm --dir web tokens && git diff --exit-code web/src/styles/tokens.css` pasan sin cambios ni advertencias.
- [x] `/proyectos/?municipio=itagui&alcobas=3` muestra solo proyectos de Itagüí con al menos una tipología vigente de 3 alcobas o más, y el "desde" de cada tarjeta es el de esa tipología (prueba de Playwright contra el catálogo ficticio).
- [x] Cambiar un filtro reescribe la URL con los parámetros de la tabla, en su orden. Abrir una ficha y volver con "Atrás" muestra los mismos filtros y resultados.
- [x] `/proyectos/?alcobas=abc&municipio=narnia` carga sin errores en la consola y, al tocar cualquier filtro, la URL ya no trae esos parámetros.
- [x] Con filtros que no deja pasar ningún proyecto se ve "Ningún proyecto cumple estos filtros", con los chips y "Limpiar todo". Al limpiar vuelven todos los proyectos.
- [x] En escritorio, el número de píldoras más los proyectos dentro de grupos es igual al número de resultados con coordenadas dentro del mapa, y el contador anuncia ese número.
- [x] Al hacer clic en una píldora, esta queda seleccionada y aparece la tarjeta flotante con enlace a la ficha. Esc la cierra y devuelve el foco a la píldora.
- [x] Al mover el mapa con el teclado (flechas sobre el mapa enfocado), cambian el contador y la lista. Con "Buscar al mover el mapa" apagado, la lista no cambia.
- [x] Los dos proyectos cercanos del catálogo aparecen como un grupo con el número 2 al alejar el mapa, y se separan al hacer clic en el grupo.
- [x] Un proyecto sin coordenadas sigue en la lista bajo "Sin ubicación publicada" cuando el filtro del mapa está activo.
- [x] Con las peticiones a `tiles.openfreemap.org` respondiendo `503`, el panel del mapa muestra "No pudimos cargar el mapa. La lista sigue funcionando." y la lista muestra todos los resultados de los filtros.
- [x] A 390 px, "Ver mapa" muestra el mapa y agrega `vista=mapa` a la URL, y "Atrás" del navegador vuelve a la lista.
- [x] Con JavaScript desactivado, `/proyectos/` muestra todos los proyectos del catálogo, y el formulario del hero lleva a `/proyectos/?municipio=…&precio_max=…`.
- [x] `@axe-core/playwright` no reporta violaciones en `/proyectos/` (lista, panel "Más filtros" abierto y vista de mapa en móvil) ni en `/` con el buscador del hero, a 390 y 1440 px.
- [x] Con el mapa cargado no hay ningún mensaje `Content Security Policy` en la consola, y la política solo suma los orígenes y fuentes del paso 5.
- [x] La atribución "OpenFreeMap © OpenMapTiles Data from OpenStreetMap" se ve en el mapa a 390 y a 1440 px.
- [x] Lighthouse CI (móvil) en `/proyectos/`: rendimiento ≥ 0,90, accesibilidad = 1,00 y CLS ≤ 0,1. El PR anota el JavaScript inicial de `/proyectos/` (gzip, sin el mapa), que debe ser ≤ 120 KB, y el del mapa, que debe ser ≤ 320 KB y cargarse solo cuando el mapa se ve.
- [x] En el HTML generado de `/proyectos/` ningún archivo contiene `"history"` (`grep -rl '"history"' web/dist` no devuelve nada).
- [x] Las páginas del 11a mantienen sus capturas, salvo las que cambian por los dos proyectos nuevos del catálogo. Esas se regeneran en Linux y el PR las muestra.
- [x] Los workflows `web.yml` y `ci.yml` quedan en verde en el PR.

## Decisiones tomadas y descartadas

- **Sí:** definición sin la ronda de preguntas de `/spec` (Andrés lo pidió para dejarlo listo de noche). Las decisiones marcadas "(sin confirmar)" se revisan antes de aprobar.
- **Sí (sin confirmar):** el 11b cubre búsqueda, filtros y mapa. **No:** dibujar zona, comparador, calculadoras y favoritos, aunque *Decisiones de diseño* e *Inventario del kit* los ponían en el 11b. Juntos tocan demasiadas áreas para un solo spec (regla de `/spec`), y cada uno tiene decisiones propias: terra-draw, fórmulas de crédito, almacenamiento local.
- **Sí:** filtrar en el navegador sobre el catálogo del build. **No:** llamar a `GET /projects` desde el navegador. La API limita a 30 listados por minuto y 600 al día por IP (SPEC 10). Mover el mapa gastaría ese cupo en minutos, y con 49 proyectos filtrar en memoria es instantáneo. Se reconsidera si el catálogo pasa de unos mil proyectos, el tope de páginas del build (`catalog.ts:10-11`).
- **Sí:** los `SearchItem` como propiedad de la isla. **No:** un JSON aparte. Con el catálogo actual pesan pocos KB comprimidos y evitan una petición y una espera.
- **Sí:** parámetros de la URL en español y legibles, como `municipio=itagui&alcobas=2`. Se pueden compartir y los lee una persona.
- **Sí:** `replaceState` para filtros y mapa, y `pushState` solo para la vista de mapa en móvil. **No:** una entrada de historial por cada filtro. "Atrás" tendría que deshacer filtro por filtro, que es uno de los errores que mide Baymard (cuaderno C3-P1).
- **Sí:** todos los filtros de tipología se cumplen en la misma tipología. **No:** mezclar tipologías, porque "3 alcobas y menos de $300 M" mostraría un proyecto cuya tipología de 3 alcobas cuesta $450 M.
- **Sí:** con filtros, el "desde" es el de la tipología que cumple. Mantiene la regla del 11a: el precio "desde" siempre va con su tipología y su fecha.
- **Sí:** MapLibre GL JS 6 directo, con OpenFreeMap. **No:** `react-map-gl` (una dependencia más para un solo mapa), MapTiler ni Stadia (sus planes gratis no permiten uso comercial), ni Google Maps (exige tarjeta). Fuente: cuaderno C4-P1.
- **Sí (sin confirmar):** estilo Positron repintado con los tokens. **No:** Liberty, que es más colorido y le compite a las píldoras. El mapa del kit es una ilustración, no un estilo real.
- **Sí:** píldoras como marcadores HTML (`<button>`), agrupadas con `supercluster`. **No:** capas de símbolos en WebGL, que no se pueden usar con el teclado (cuaderno C4-P1).
- **Sí (sin confirmar):** en móvil, alternar entre lista y mapa como en el kit (*Search Result (Swipe Up)* y *Search Map v2*). **No:** la hoja inferior con tres anclajes de Airbnb, que se deja para un spec propio. *Decisiones de diseño* ya decía "Móvil: después de este spec".
- **No:** esqueletos al mover el mapa, aunque *Decisiones de diseño* los pedía. El filtro es instantáneo y un esqueleto artificial solo retrasaría el resultado. Solo hay esqueletos mientras carga el mapa o mientras hidrata una URL con filtros.
- **No:** filtros por entrega, VIS o subsidio. La API no tiene esos datos (`docs/schema.md:132`).
- **No:** vista satelital, "mi ubicación", capas de Metro y edificios en 3D. No hay satélite gratis, la ubicación pide permiso al visitante y las capas necesitan datos propios (cuaderno C4-P1).
- **No (sin confirmar):** el control segmentado por municipio del inicio que el 11a dejaba para este spec. El buscador del hero ya filtra por municipio, y dos controles para lo mismo sobran.
- **Sí:** el buscador del hero como formulario `GET` sin JavaScript. El inicio sigue sin islas.

## Riesgos identificados

| Riesgo | Mitigación |
| --- | --- |
| OpenFreeMap lo opera una sola persona, sin acuerdo de servicio | El mapa caído no rompe la búsqueda: hay un estado de error y la lista sigue funcionando. Plan B documentado: un PMTiles del Valle de Aburrá en Cloudflare R2, cambiando solo la URL del estilo (cuaderno C4-P1) |
| MapLibre pide más permisos de CSP de los previstos (`blob:` en workers) | El paso 5 lo prueba en el navegador. Cualquier permiso nuevo se anota con su motivo en `docs/security.md` |
| El JavaScript del mapa baja el rendimiento en celular | El mapa se carga con `import()` solo cuando se ve. En móvil, solo al tocar "Ver mapa". Los presupuestos van en los criterios |
| Las pruebas dependen de la red o salen inestables por las teselas | Estilo local sin red, con `page.route`, y capturas con ese estilo |
| Hay demasiados marcadores HTML si el catálogo crece | `supercluster` limita los marcadores en pantalla. Por encima de unos 1.000 proyectos se revisa la decisión de filtrar en el navegador |
| Parpadeo de la lista sin filtros antes de hidratar | El `<script is:inline>` del paso 3 muestra esqueletos mientras hidrata una URL con filtros |
| Los dos proyectos nuevos del catálogo mueven capturas y cifras del 11a | Se regeneran en el mismo PR y se muestran lado a lado |

## Lo que **no** entra en este spec

- Dibujar zona, comparador, calculadoras y favoritos.
- Hoja inferior de tres anclajes en móvil y vista de lista horizontal.
- Filtros por entrega, VIS o subsidio.
- Puntos de interés, 3D, satélite y "mi ubicación".
- Teselas propias en PMTiles.
- Asesor en la web (11c) y despliegue (SPEC 12).

Cada uno, si llega, va en su propio spec.
