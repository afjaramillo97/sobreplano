# SPEC 11a — Base del frontend, ficha del proyecto y listado

> **Estado:** implementado
> **Depende de:** SPEC 07, SPEC 10
> **Fecha:** 2026-11-24
> **Objetivo:** Crear el sitio estático de Sobreplano en `web/` (Astro con islas de React y el diseño del kit Estatery tal cual, con solo los cambios necesarios) con inicio, listado y ficha de cada proyecto con su histórico de precios, probado en CI con un catálogo ficticio.

## Por qué existe este spec

Sobreplano tiene API, scraper, asesor y evals, pero nadie puede verlo sin `curl`. El histórico de precios, que es el diferencial, solo existe como JSON. Este spec pone la primera cara del producto: la ficha honesta del precio "desde" (feature A1 del backlog) y un listado para llegar a ella.

El diseño ya está decidido fuera del repo:

- Stack y reglas: *Propuesta curada del frontend (SPEC 11)*, 17 nov, construida con los cinco cuadernos de investigación (C1 a C5).
- Kit, paleta, fotos y vista de mapa: *Decisiones de diseño del frontend (SPEC 11)*, 20 a 23 nov.
- Flujo de trabajo con el kit: *Flujo de diseño e implementación del frontend (SPEC 11)*, 23 nov.
- Tokens: `~/Documents/investigación Fronted/tokens-sobreplano.draft.json` (revisado el 24 nov en la noche) y *Tokens del sistema de diseño (fase 1)*. La paleta descartada queda en `tokens-sobreplano.draft.atardecer-marino.json` y no se usa.

Decisiones de Andrés del 24 nov que este spec aplica: el histórico sigue protegido por la API, el sitio le habla al usuario de **tú**, y no hay fotos todavía, así que cada proyecto lleva una imagen por defecto acorde al diseño.

Revisión de Andrés del 24 nov en la noche, que reemplaza lo anterior donde choca:

- **El kit Estatery se usa tal cual.** Solo se cambia lo necesario: contraste AA, contenido que sería inventado y el logo, que la licencia no permite. Se descarta la paleta "Atardecer marino" (se veía muy oscura y se alejaba del kit). La comparación pantalla por pantalla está en el lienzo "Sobreplano · Kit Estatery con cambios mínimos", página "Kit vs. Sobreplano".
- **Los recursos del kit sí se usan** (iconos e ilustraciones), desde un repo privado. El repo público solo tiene código.
- **No hay página de metodología.** Podría revelar secretos del negocio.

Estado actual del repo (`main` en `2b098b6`; desde `b1a43bb` solo entraron actualizaciones de Dependabot, así que estas referencias siguen vigentes):

- `CLAUDE.md:16` y `CLAUDE.md:34` todavía dicen "React + Vite, tRPC BFF". No existe `web/`.
- `src/sobreplano/interface/api/main.py:41-53`: la app no tiene CORS. Un navegador en otro origen no puede leer `GET /projects/{slug}`.
- `src/sobreplano/interface/api/main.py:46`: `/openapi.json` se apaga en producción (`api_docs_enabled`, `settings.py:40`). El cliente tipado no puede bajar el contrato de la API desplegada.
- `src/sobreplano/interface/api/routes/projects.py:18-20`: `limit` hasta 50, `offset` hasta 1000. `:59-69`: el detalle con histórico, con su propio límite (`rate_limit.py:160`).
- `src/sobreplano/interface/api/rate_limit.py:131`: el `429` trae `Retry-After`. Un navegador solo puede leer esa cabecera si CORS la expone.
- `src/sobreplano/interface/api/schemas.py:63-76`: cada tipología trae `latest_price`, `first_price`, `change_since_first_pct` (porcentaje con un decimal, `domain/listings.py:58-72`), `price_per_m2_cop` y `area_basis`. `schemas.py:116-126`: el proyecto trae `location` nulo cuando la constructora no publica mapa.
- `docs/schema.md:114`: una observación por tipología por día. Una tipología que dejó de publicarse conserva su último precio con una fecha vieja.
- `evals/advisor/catalog.json`: 9 proyectos ficticios. No tiene tipologías solo con área construida, ni barrio, ni tipologías que dejaron de publicarse, y su historia más larga tiene 4 precios. Cambiarlo movería el golden set del asesor.
- `src/sobreplano/interface/cli/seed.py:92`: el seed acepta `--file`. `seed_schema.py:39-50` y `:86-98` admiten `built_area_m2`, `neighborhood`, `lat`/`lon` opcionales e `history`.

## Alcance

**Dentro:**

- **Proyecto `web/`:** Astro 7 en salida estática, islas de React 19, TypeScript estricto, Tailwind v4, shadcn/ui sobre Radix, pnpm, Node 24.
- **Sistema de diseño en el repo:**
  - tokens DTCG en `web/tokens/sobreplano.tokens.json`, generados a `web/src/styles/tokens.css` (`@theme` de Tailwind y variables de shadcn);
  - test de contraste de los pares de color declarados;
  - `web/DESIGN.md` con las reglas verificables;
  - regla de CI que rechaza colores, radios, sombras y fuentes fuera de los tokens.
- **Cliente de la API:** contrato exportado desde el código (`openapi.json` en el repo), tipos con `openapi-typescript`, llamadas con `openapi-fetch`. Un test de Python falla si el contrato cambia sin regenerarlo.
- **Formatos `es-CO`** en `web/src/lib/format.ts`, con tests.
- **Páginas:**
  - `/`: hero, los que más han subido, banda de cifras reales;
  - `/proyectos/`: listado en cuadrícula, sin filtros;
  - `/proyectos/[slug]/`: ficha completa con la gráfica del histórico como isla;
  - `/terminos/`: los términos de uso de `docs/terms-of-use.md`;
  - `404`.
- **Imagen por defecto** de proyecto (SVG propio, no del kit) y textos honestos sobre la falta de fotos.
- **Recursos del kit** (iconos e ilustraciones exportados como SVG desde Figma) en el repo privado `sobreplano-kit`, conectado como submódulo en `web/kit/`, con iconos de reemplazo propios para compilar sin acceso.
- **`og:image` por proyecto** generada en el build.
- **SEO básico:** título y descripción por página, `sitemap.xml` y `robots.txt` del sitio.
- **CSP** con la función nativa de Astro (`security.csp`).
- **Backend:** CORS configurable con `Retry-After` expuesto; CLI `export_openapi`; catálogo ficticio del frontend.
- **Calidad en CI** (workflow nuevo `web.yml`): `astro check`, Vitest, build contra la API local con el catálogo ficticio, Playwright con axe y capturas a 390 y 1440 px, Lighthouse CI con presupuestos, `pnpm audit`.
- **Documentación:** `CLAUDE.md`, `README.md`, `docs/security.md` y Dependabot para `web/`.

**Fuera (para specs futuros):**

- Búsqueda con filtros en la URL, mapa con MapLibre, dibujar zona, comparador, calculadoras y bloque "¿Me alcanza?" (11b).
- Asesor en la web (11c).
- Logo en SVG y precarga animada (spec propio, cuando el logo esté aprobado). Mientras tanto, una marca provisional en texto.
- Favoritos y compartir: los botones del kit esperan a las cuentas.
- Buscador del hero y control segmentado por municipio: se pintan cuando funcionen (11b).
- Fotos reales: URLs de imágenes en el scraper y galería (spec propio).
- Despliegue, previews en Cloudflare, dominio, cabeceras `_headers`, Turnstile, reconstrucción diaria y analítica (SPEC 12).
- Versión en inglés.
- Modo oscuro (los tokens quedan listos, la interfaz no).

## Modelo de datos

### 1. Contrato de la API (`web/src/lib/api/`)

- `openapi.json`: lo escribe `uv run python -m sobreplano.interface.cli.export_openapi` desde `create_app().openapi()`, con claves ordenadas y sangría de 2. No depende de que `/openapi.json` esté encendido.
- `schema.d.ts`: lo genera `pnpm api:types` (`openapi-typescript`). Se versiona.
- `client.ts`: un `createClient<paths>()` de `openapi-fetch` para el build (`SOBREPLANO_API_URL`) y otro para el navegador (`PUBLIC_API_URL`).
- `tests/unit/interface/test_openapi_snapshot.py` compara `create_app().openapi()` con el archivo del repo. Si alguien cambia la API sin regenerar, CI falla.

### 2. Modelo de vista (`web/src/lib/projects.ts`)

Se calcula en el build a partir de `ProjectOut`. No hay aritmética de precios en los componentes.

```ts
type UnitTypeView = {
  id: string;
  name: string;
  bedrooms: number | null;
  bathrooms: number | null;
  areaM2: number;                 // privada si existe, si no construida
  areaBasis: "private" | "built";
  priceCop: number | null;        // último precio, solo si la tipología está vigente
  pricePerM2Cop: number | null;
  observedOn: string | null;      // fecha ISO de la última observación
  firstPrice: { priceCop: number; observedOn: string } | null;
  changePct: number | null;       // tal cual la API, un decimal
  status: "current" | "not-published" | "no-price";
};

type ProjectView = {
  slug: string;
  name: string;
  developer: { name: string; slug: string };
  municipality: Municipality;
  neighborhood: string | null;
  location: { lat: number; lon: number } | null;
  sourceUrl: string;
  lastObservedOn: string | null;  // la fecha más reciente entre sus tipologías
  from: UnitTypeView | null;      // la tipología vigente más barata
  unitTypes: UnitTypeView[];      // vigentes primero, por precio; luego el resto, por nombre
};
```

Reglas:

- **Tipología vigente:** su última observación es del mismo día que `lastObservedOn`. La regla sale de `docs/schema.md:114` (una observación por día mientras se publica).
- **`not-published`:** tiene precio, pero su última observación es anterior a `lastObservedOn`. Se muestra como "No publicada desde el 3 nov 2026", sin precio actual, y no cuenta para el "desde".
- **`no-price`:** nunca tuvo precio.
- **"Desde":** el menor `priceCop` entre las vigentes, siempre con el nombre de su tipología y su fecha. Si no hay vigentes, la ficha dice "Sin precio publicado" y la tarjeta también.
- **`changePct` del proyecto:** el de la tipología del "desde". Nunca un promedio.

### 3. Formatos (`web/src/lib/format.ts`)

Todo con `Intl` y `es-CO`. Los valores exactos, incluido el espacio duro (` `) que produce `Intl`, quedan en los tests.

| Función | Entrada | Salida |
| --- | --- | --- |
| `formatCop` | `380000000` | `$ 380.000.000` |
| `formatMillions` | `445000000` | `$ 445 millones` (y `$ 1.250 millones`) |
| `formatPct` | `12.5`, `-3` | `+12,5 %`, `−3,0 %` (signo menos tipográfico) |
| `formatArea` | `58.5` | `58,5 m²` |
| `formatDate` | `2026-11-02` | `2 nov 2026` |
| `formatDateShort` | `2026-11-02` | `02/11/2026` (tablas) |

Las fechas de la API son días (`date`), sin hora. Se formatean con `timeZone: "UTC"` para que un navegador en otra zona no muestre el día anterior.

### 4. Tokens (`web/tokens/` y `web/src/styles/`)

- `sobreplano.tokens.json`: el borrador revisado del 24 nov (kit tal cual: morado `#685DE8`, secundario `#100A55`, morados 90 a 98, texto `#000929`, `#4D5369` y `#666B7F`, bordes de 1,5 px), sin cambios de valores. Grupos `color`, `font`, `typography`, `space`, `radius`, `border-width`, `shadow`, `size`, `duration`, `easing`.
- `web/scripts/build-tokens.mjs` (sin dependencias) escribe `tokens.css` con:
  - un bloque `@theme` con los primitivos y la escala;
  - variables semánticas en `:root` (`--color-bg-canvas`, `--color-action`, `--color-change-bg`, …);
  - las variables que usa shadcn (`--background`, `--foreground`, `--primary`, `--ring`, `--radius`, …) apuntando a las semánticas.
- `web/tokens/contrast-pairs.json`: los pares que deben cumplir AA (texto y fondo, borde y fondo, foco). Como mínimo: `text.primary`, `text.secondary` y `text.muted` sobre blanco, `bg.subtle` y `bg.selected`; `text.price` sobre blanco; blanco sobre `action.default`, `action.hover` y `action.dark`; `action.soft-text` sobre `action.soft`; `change.text` sobre `change.bg`; los tres colores de `headline-gradient` sobre el fondo del hero (3:1, texto grande); `focus.ring` sobre blanco (3:1). El borde de los campos queda fuera, como excepción documentada en `DESIGN.md`. Un test de Vitest calcula el contraste WCAG de cada par y exige 4,5:1 en texto y 3:1 en bordes, iconos y foco.
- CI corre el script y falla si `tokens.css` cambia (`git diff --exit-code`).

### 5. Reglas de diseño verificables (`web/DESIGN.md` y `web/scripts/check-design-rules.mjs`)

`DESIGN.md` reúne las reglas. Donde el kit decide, manda el kit; las de la *Propuesta curada* (§3) solo aplican donde el kit no dice nada:

1. Fuente única: Plus Jakarta Sans variable, servida desde el sitio (`@fontsource-variable/plus-jakarta-sans`). Sin llamadas a Google Fonts.
2. Precios en `text.price` (el morado del kit), `price-lg` y `price` (800, tracking −1 px), cifras proporcionales en tarjetas. `tabular-nums` en tablas y en cifras que se alinean en columna.
3. Radios solo de la escala del kit (4, 8, 16, completo; 6 en el segmento interno). Bordes de 1,5 px, y de 2 px en campos y botones de contorno. Sombras solo `shadow.sm` y `shadow.float`.
4. Colores solo de los tokens: acción `#685DE8` (hover y texto sobre lavanda `#5245ED`) y botón oscuro `#100A55`. La variación de precio va en la insignia morada del kit (la forma de POPULAR), nunca en verde ni en rojo.
5. Sin tarjetas dentro de tarjetas ni numeración 01/02/03. La insignia del kit solo muestra la variación de precio, nunca "Popular". Sin testimonios, calificaciones ni cifras que no salgan de los datos.
6. El precio "desde" nunca aparece sin su tipología, su fecha y el aviso de lo que puede no incluir.
7. Errores con causa y salida, sin disculpas. Estados vacíos con una acción.
8. Movimiento de 120 a 400 ms (tokens `duration`), sin rebote, apagado con `prefers-reduced-motion`.
9. Textos en español de Colombia, con tuteo, sin mezclar con "usted".
10. El único texto con degradado es la segunda parte del título del inicio, con los tokens `headline-gradient`.
11. Excepción conocida: el borde de los campos del kit (`#E0DEF7`) no llega a 3:1 contra el blanco. Se conserva, con etiqueta visible, relleno lavanda y anillo de foco `#685DE8` (4,86:1).

`check-design-rules.mjs` recorre `web/src/**/*.{astro,tsx,ts,css}` (sin `tokens.css` ni `components/ui/`) y falla con archivo y línea si encuentra:

- utilidades con la paleta por defecto de Tailwind (`(bg|text|border|ring|fill|stroke|from|via|to)-(slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-\d{2,3}`);
- valores hexadecimales o `rgb(`/`hsl(`/`oklch(` sueltos;
- `rounded-` o `shadow-` que no sean de la escala de tokens;
- `font-` con otra familia, o los nombres Inter, Roboto, Poppins, Montserrat o Playfair.

Los componentes generados por shadcn en `components/ui/` se revisan una vez al agregarlos y se ajustan a los tokens. Quedan fuera del chequeo porque su código usa clases semánticas (`bg-primary`), no colores sueltos.

### 6. Catálogo ficticio del frontend (`web/tests/fixtures/catalog.json`)

Mismo formato que `seeds/projects.json` (lo valida `seed_schema.py`). Todos los dominios son `example.com`. Fechas fijas, para capturas deterministas. Al menos 12 proyectos que cubren:

| Caso | Para qué |
| --- | --- |
| Historia larga (6 cambios o más en 4 meses o más, con días repetidos) | Gráfica escalonada y tabla del histórico |
| Bajada de precio | Insignia "BAJÓ" con signo negativo |
| Una sola observación | "Aún no hay cambio que mostrar" |
| Tipología solo con área construida | `$/m²` con "sobre área construida" |
| Tipología que dejó de publicarse | Estado `not-published` y "desde" que no la cuenta |
| Tipología que nunca tuvo precio | Estado `no-price` |
| Proyecto sin ningún precio vigente | "Sin precio publicado" en tarjeta y ficha |
| Proyecto sin coordenadas | "Sin ubicación publicada", sin enlaces de mapa |
| Proyecto con barrio y proyecto sin barrio | Línea de ubicación con y sin barrio |
| Nombre de 40 caracteres o más | Cortes de línea en tarjeta, ficha y `og:image` |
| Cinco municipios distintos y tres constructoras | Banda de cifras y variedad del listado |

Se carga con `uv run --env-file .env python -m sobreplano.interface.cli.seed --file web/tests/fixtures/catalog.json` sobre una base local recién migrada.

### 7. Cambios de backend

**CORS** (`main.py`):

- `Settings` suma `cors_allowed_origins: list[str] = []` (variable `CORS_ALLOWED_ORIGINS`, lista JSON).
- `create_app` agrega `CORSMiddleware` solo si la lista no está vacía, con `allow_methods=["GET"]`, `allow_credentials=False` y `expose_headers=["Retry-After"]`.
- Sin comodín `*`. El asesor (POST) se suma en 11c.

**Exportar el contrato** (`src/sobreplano/interface/cli/export_openapi.py`): escribe `web/src/lib/api/openapi.json`; `--check` sale con 1 si el archivo del repo difiere. Docstring de módulo y de función, como pide `CLAUDE.md`.

### 8. Páginas

| Ruta | Contenido | Ancla del kit | JavaScript |
| --- | --- | --- | --- |
| `/` | Hero claro del kit (degradado lavanda): título "Descubre el mercado inmobiliario inteligente con IA" en tres líneas (Andrés, 24 nov), con la última parte en el degradado `headline-gradient` (violeta, rosa y azul lavanda, cada color con 3,6:1 o más sobre el fondo); subtítulo, botón "Ver proyectos" en el lugar del buscador (el buscador llega en 11b), dos cifras reales con los círculos del kit (proyectos seguidos y días de historia) y, a la derecha, la imagen por defecto en grande con la tarjeta del proyecto que más ha subido (en lugar del testimonio) y la caja oscura "Datos diarios" con la fecha de la última revisión (en lugar de Trustpilot); bloque "La forma honesta de comprar sobre plano" con cuatro ventajas e iconos del kit; "Los que más han subido" (hasta 3 tarjetas, solo con `changePct` positivo, por cambio descendente; sin la sección si no hay ninguno) y botón oscuro "Ver más proyectos" | Landing Page v1 | Ninguno |
| `/proyectos/` | Encabezado "N proyectos"; cuadrícula de tarjetas L (3 columnas a 1440, 1 a 390), ordenadas por "desde" ascendente y sin precio al final | Property Listings | Ninguno |
| `/proyectos/[slug]/` | Ver abajo | View Property Details | Isla de la gráfica (`client:visible`) |
| `/terminos/` | `docs/terms-of-use.md` tal cual, leído en el build | — | Ninguno |
| `404` | Causa y dos salidas: listado e inicio | Empty state | Ninguno |

**Navegación** (96 px, 72 en móvil, fondo `bg.nav`): marca provisional en texto, enlace "Proyectos" y botón primario "Ver proyectos". En móvil, el menú de dos líneas del kit abre los mismos enlaces. El asesor se suma en 11c.

**Pie** (el del kit): marca, columnas "Proyectos" (listado) y "Legal" (términos de uso) y la línea de derechos. Sin redes sociales ni enlaces que no existan.

**Ventajas del inicio**, con iconos del kit en círculo lavanda:

| Icono | Título | Texto |
| --- | --- | --- |
| `chart-outline` | Historial diario | Guardamos el precio de cada tipología todos los días, desde que la vimos publicada. |
| `dollar-square-outline` | Precio sin letra pequeña | Cada "desde" dice de qué tipología es, de qué fecha y qué puede no incluir. |
| `message-outline` | Asesor con fuentes | Pregunta en español y mira de dónde sale cada dato de la respuesta. (Mientras no exista el asesor en la web, 11c, esta ventaja no se muestra.) |
| `property-insurance-outline` | No vendemos proyectos | No cobramos a las constructoras ni mostramos anuncios pagados. |

Las cifras del hero usan `properties-outline` (proyectos seguidos) y `calendar-outline` (días de historia).

**Tarjeta de proyecto** (`ProjectCard.astro`, la tarjeta L del kit: 352 de ancho, imagen de 200 de alto, borde 1,5 `#F0EFFB`): imagen por defecto; insignia de variación cuando hay `changePct` ("SUBIÓ 9,8 %" o "BAJÓ 2,1 %"); "desde" y el precio en `price-lg` morado; nombre; constructora, municipio y barrio; divisor; facilidades de la tipología del "desde" con los iconos del kit (alcobas, baños, área) y la fecha del precio. Sin botón de favorito. Toda la tarjeta es un enlace a la ficha, con un solo foco.

**Ficha** (contenedor 1120, columnas 784 + 32 + 376):

- **Cabecera:** migas (Proyectos › nombre), nombre (`h1`), constructora, municipio y barrio. Sin coordenadas: "Sin ubicación publicada".
- **Imagen:** la imagen por defecto y el texto "Imagen ilustrativa. Aún no tenemos fotos de este proyecto. Puedes verlas en el sitio de {constructora}", con enlace a `source_url`.
- **Ficha técnica** (la del kit, 784 de ancho): alcobas, baños y área de la tipología del "desde", entrega y estado, con los iconos del kit.
- **Tarjeta de precio** (columna de 376, fija al hacer scroll en escritorio):
  - "Desde {millones}", tipología y "observado el {fecha}";
  - insignia de variación y "desde el primer precio, el {fecha}";
  - aviso fijo: "Precio desde publicado por la constructora el {fecha}. Puede no incluir parqueadero, cuarto útil, acabados ni gastos de escrituración.";
  - botón "Ver en el sitio de {constructora}" (`source_url`, `rel="noopener"`).
- **Histórico** (isla `HistoryChart`):
  - selector de tipología (pestañas de Radix), con la del "desde" escogida;
  - línea escalonada (`type="stepAfter"`), eje X con fechas reales, huecos en días sin observación (`connectNulls={false}`);
  - eje Y recortado con mínimo y máximo visibles;
  - resumen en texto visible ("Subió 12,5 % entre el 7 sep y el 2 nov 2026");
  - tabla del histórico solo con los días en que cambió el precio, con fecha, precio y cambio, en `tabular-nums`. Es también la alternativa accesible de la gráfica.
- **Tipologías:** tabla con nombre, alcobas, baños, área (con "privada" o "construida"), precio, `$/m²` con su base, variación y estado.
- **Ubicación:** con coordenadas, enlaces "Abrir en Google Maps" y "Cómo llegar" (`https://www.google.com/maps/search/?api=1&query=lat,lon` y `/dir/?api=1&destination=lat,lon`). El mapa embebido va en 11b.
- **Fuente:** enlace a la ficha del proyecto en el sitio de la constructora.

**Estados de la isla del histórico:**

| Estado | Qué ve el usuario |
| --- | --- |
| Cargando | Esqueleto del tamaño final de la gráfica (sin salto de diseño) |
| Una sola observación | "Solo tenemos el precio del {fecha}. La gráfica aparece cuando cambie." |
| `429` | "Consultaste muchas fichas en poco tiempo. Podrás ver la gráfica a las {hora de Retry-After}." La tarjeta de precio y la tabla de tipologías siguen visibles, porque vienen en el HTML |
| Error o API caída | "No pudimos cargar el histórico. Reintentar." con un botón |

**Consulta del histórico:** TanStack Query con `staleTime: Infinity`, `refetchOnWindowFocus: false` y reintento solo una vez para errores 5xx o de red. Nunca reintenta un `429` ni un `404`: cada reintento gasta el límite diario del usuario.

### 9. Imagen por defecto (`web/src/assets/project-placeholder.svg`)

- SVG original, hecho en código (borrador aprobado en el lienzo, 2,2 KB, en `~/Documents/investigación Fronted/project-placeholder.svg`): edificio isométrico en los morados del kit, con los pisos de arriba en línea punteada ("sobre plano"), una grúa en `#100A55` y fondo `#F0EFFB`.
- Proporción 16:9 y recorte por `object-fit: cover` en tarjeta y ficha. Menos de 4 KB.
- Es decorativa (`alt=""`). La información está en el texto.
- No usa recursos del kit, así que no depende del submódulo. Si Andrés genera en Google Flow una ilustración en el mismo estilo, puede reemplazarla; nunca una foto realista, que haría creer que así se ve el proyecto.

### 10. `og:image` (`web/src/pages/og/[slug].png.ts`)

- PNG de 1200×630 por proyecto, generado en el build con `satori` y `@resvg/resvg-js`.
- Fondo lavanda del hero del kit, nombre, municipio, "Desde {millones}" en morado, insignia de variación y "Precio observado el {fecha}". Marca en texto.
- Fuente: los archivos WOFF de `@fontsource/plus-jakarta-sans` (700 y 800). `satori` no lee WOFF2.
- Sin precio vigente: muestra el nombre y "Sin precio publicado".

### 11. CSP

- `security.csp` de Astro en `astro.config.mjs`. Astro calcula los hashes de sus scripts y estilos y escribe la política en un `<meta>`.
- Directivas: `default-src 'self'`, `img-src 'self' data:`, `font-src 'self'`, `connect-src 'self'` más el origen de `PUBLIC_API_URL`, `object-src 'none'`, `base-uri 'self'`, `form-action 'self'`.
- Una política en `<meta>` no admite `frame-ancestors` ni reportes. Esas dos van como cabeceras en el SPEC 12.

## Plan de implementación

1. **CORS y contrato.** `cors_allowed_origins` en `Settings`, `CORSMiddleware` en `create_app`, `export_openapi` con `--check`, `test_cors.py` (origen permitido, origen ajeno, `Retry-After` expuesto en un `429`, sin CORS con la lista vacía) y `test_openapi_snapshot.py`. `.env.example` con `CORS_ALLOWED_ORIGINS`. Commit `feat:`.
2. **Esqueleto de `web/`.** `pnpm create astro` en modo vacío, React, Tailwind v4, `tsconfig` con `astro/tsconfigs/strictest`, `.nvmrc` con 24, `packageManager` fijado, `minimumReleaseAge` de 1440 minutos, scripts (`dev`, `build`, `check`, `test`, `e2e`, `tokens`, `rules`, `api:types`). Página vacía que compila. Commit `chore:`.
3. **Tokens, reglas y recursos del kit.** Submódulo privado `web/kit/` (`git submodule add` del repo `sobreplano-kit`, que Andrés crea y llena con los SVG exportados desde Figma); `web/src/lib/icons.ts` carga cada icono desde `web/kit/icons/` (115 SVG del set "Icon" del kit con `currentColor`, nombres `<nombre>-<outline|bold>.svg` e índice en `INDEX.md`; los del 11a son `bed-outline`, `bath-outline`, `square-meters-outline`, `search-outline`, `chevron-left-outline`, `filter-outline`, `map-outline` y `check-circle-outline`) con `import.meta.glob` y, si no está, usa el de reemplazo en `web/src/assets/icons-fallback/`. `sobreplano.tokens.json`, `build-tokens.mjs`, `tokens.css`, `contrast-pairs.json` con su test, `check-design-rules.mjs`, `DESIGN.md`. `shadcn init` con las variables de `tokens.css`; botón, pestañas, tabla y esqueleto revisados contra los tokens. Commit `feat:`.
4. **Datos.** `openapi.json` exportado, `schema.d.ts`, `client.ts`, `format.ts` y `projects.ts` con sus tests de Vitest (todos los formatos, la regla de vigencia, el "desde" y el orden de tipologías). Commit `feat:`.
5. **Catálogo ficticio.** `web/tests/fixtures/catalog.json` con los casos de la sección 6, cargado en local con el seed. Commit `test:`.
6. **Layout y componentes.** `BaseLayout.astro` (`lang="es-CO"`, fuente, metadatos, `scroll-padding-top` de 96), navegación de 96 px (72 en móvil), pie, `ProjectCard`, `PriceChangeBadge`, `ProjectImage` con la imagen por defecto, `PriceCard`, `UnitTypesTable`. Commit `feat:`.
7. **Listado, inicio y páginas de texto.** `/proyectos/`, `/`, `/terminos/` y `404`, con los datos del build (paginando `GET /projects` de 50 en 50 hasta `total`). Commit `feat:`.
8. **Ficha e histórico.** `/proyectos/[slug]/` con `getStaticPaths`, isla `HistoryChart` con TanStack Query y shadcn Chart (Recharts), sus cuatro estados y la tabla del histórico. Commit `feat:`.
9. **SEO, `og:image` y CSP.** Metadatos por página, `@astrojs/sitemap`, `robots.txt` del sitio, `og/[slug].png.ts`, `security.csp`. Commit `feat:`.
10. **Pruebas de navegador.** Playwright con `@axe-core/playwright` en todas las páginas, navegación con teclado de la ficha, estados `429` y error con `page.route`, capturas a 390 y 1440 px generadas en Linux con la imagen oficial de Playwright, sin scroll horizontal a 320 px. Lighthouse CI con `lighthouserc.json`. Commit `test:`.
11. **CI y dependencias.** `.github/workflows/web.yml` (acciones fijadas por SHA): checkout con el submódulo usando el secreto `KIT_REPO_TOKEN` (token de solo lectura limitado a `sobreplano-kit`; sin el secreto, como en un fork, compila con los iconos de reemplazo), Python, Supabase, migraciones, seed del catálogo ficticio, API en segundo plano con `RATE_LIMITS_ENABLED=false` y `CORS_ALLOWED_ORIGINS=["http://localhost:4321"]`, `pnpm install --frozen-lockfile`, `pnpm audit --prod --audit-level high`, tokens y reglas sin cambios, `astro check`, Vitest, build, Playwright y Lighthouse. Corre en PR que tocan `web/**`, `src/sobreplano/interface/api/**` o el workflow. Dependabot con `npm` en `/web`. Commit `ci:`.
12. **Documentación.** `CLAUDE.md`: stack del frontend, carpeta `web/`, comandos de `web/`, enlace a `web/DESIGN.md` y la regla "nunca subir archivos del kit Estatery al repo público (`.fig`, PNG, iconos, ilustraciones, fotos); van en el repo privado `sobreplano-kit`" en *Never break*. `README.md`: el frontend y "Interfaz basada en el UI kit Estatery de DhuhaCreative (UI8)". `docs/security.md`: CORS y CSP en el activo "histórico de precios", y lo que queda para el SPEC 12. `docs/deploy.md`: el submódulo `web/kit/` y el secreto `KIT_REPO_TOKEN` (token de GitHub de solo lectura, limitado a `sobreplano-kit`, vence el 22 feb 2027) con cómo renovarlo. Commit `docs:`.

Ningún paso tiene llamadas pagas.

## Criterios de aceptación

Cada criterio se verifica pegando el comando y su salida en el PR (constitución, principio 6). Los commits van en inglés.

- [x] `uv run pytest tests/unit/interface/test_cors.py tests/unit/interface/test_openapi_snapshot.py` pasa.
- [x] Con `CORS_ALLOWED_ORIGINS='["http://localhost:4321"]'`, `curl -si -H "Origin: http://localhost:4321" localhost:8000/projects?limit=1` trae `access-control-allow-origin: http://localhost:4321`. Con `-H "Origin: https://evil.example"` no la trae.
- [x] `uv run python -m sobreplano.interface.cli.export_openapi --check` sale con 0, y sale con 1 tras agregar un campo de prueba a `UnitTypeOut` (probado y revertido).
- [x] `pnpm --dir web tokens && git diff --exit-code web/src/styles/tokens.css` no muestra cambios.
- [x] `pnpm --dir web rules` pasa, y falla con archivo y línea al agregar `bg-indigo-600` o `#7065F0` a un componente (probado y revertido).
- [x] `pnpm --dir web check` termina con 0 errores y 0 advertencias.
- [x] `pnpm --dir web test` pasa, incluidos los formatos exactos de la sección 3 y todos los pares de `contrast-pairs.json`.
- [x] `pnpm --dir web build` con la API local y el catálogo ficticio genera una ficha y una `og:image` por proyecto (`ls web/dist/proyectos | wc -l` y `ls web/dist/og | wc -l` igual al número de proyectos). _(12 fichas y 12 `og:image`; `ls web/dist/proyectos` da 13 porque también cuenta el `index.html` del listado)_
- [x] `grep -L "astro-island" web/dist/index.html web/dist/proyectos/index.html web/dist/terminos/index.html` lista los tres archivos: esas páginas no cargan JavaScript de islas.
- [x] El histórico no queda en el sitio estático: `grep -rl '"history"' web/dist` no devuelve nada, y la isla recibe solo el `slug` como propiedad.
- [x] La ficha del proyecto sin precio vigente dice "Sin precio publicado"; la tipología que dejó de publicarse dice "No publicada desde el …" y no es el "desde" (prueba de Playwright).
- [x] Con `page.route` respondiendo `429` y `Retry-After: 120`, la isla muestra el mensaje con la hora y la tarjeta de precio sigue visible. Con `500`, muestra "Reintentar" y el botón vuelve a pedir.
- [x] En el test del `429`, el navegador hace una sola petición al detalle (sin reintentos), contada con `page.on("request")`.
- [x] `@axe-core/playwright` no reporta violaciones en `/`, `/proyectos/`, dos fichas (con y sin coordenadas), `/terminos/` y la 404, a 390 y 1440 px.
- [x] En la ficha, con solo el teclado se llega a las pestañas de tipología, se cambia de tipología con las flechas y el foco es visible en todo momento (prueba de Playwright).
- [x] A 320 px de ancho, ninguna página tiene scroll horizontal (`document.documentElement.scrollWidth <= 320`).
- [x] Las capturas de Playwright de inicio, listado y dos fichas, a 390 y 1440 px, están aprobadas y versionadas en `web/tests/e2e/**-snapshots/`, y el PR muestra al lado la pantalla equivalente del kit (fuera del repo) para la revisión visual. _(aprobadas por el dueño el 2026-11-25, tras corregir en el PR #32 la "g" recortada del título, el espaciado de la línea "Tipo 1 · precio del…" y la tabla de tipologías cortada a 1440 px)_
- [x] Lighthouse CI (móvil) en `/`, `/proyectos/` y una ficha: rendimiento ≥ 0,90, accesibilidad = 1,00, buenas prácticas ≥ 0,95, SEO ≥ 0,95, LCP ≤ 2,5 s y CLS ≤ 0,1. El PR anota los KB de JavaScript de la ficha (gzip) y queda bajo 250 KB. _(1,00 en las cuatro categorías en las tres páginas, LCP ≤ 1,05 s y CLS 0; la ficha carga 219 KB de JavaScript gzip con recharts 3.11, solo cuando el histórico entra en pantalla)_
- [x] Ninguna página muestra errores de CSP en la consola del navegador en `pnpm preview` (Playwright falla ante un mensaje `Content Security Policy`).
- [x] `git ls-files | grep -iE '\.fig$|estatery'` no devuelve nada, y `git ls-files web/kit` lista solo el submódulo.
- [x] Sin el submódulo (`git submodule deinit -f web/kit`), `pnpm --dir web build` termina y usa los iconos de reemplazo (probado y revertido). _(el build avisa `[icons] web/kit is missing: building with the fallback icons`)_
- [x] El workflow `web.yml` queda en verde en el PR, y `ci.yml` también. _(verde en los PR #28 y #32, con el kit; en los PR de Dependabot las capturas se saltan si falta `KIT_REPO_TOKEN` como secreto de Dependabot)_

## Decisiones tomadas y descartadas

- **Sí:** Astro 7. **No:** Astro 6, como decía la *Propuesta curada*. Astro 7 salió el 22 jun 2026 (compilador en Rust, Vite 8) y la rama vigente es la 7.4. Empezar en la 6 sería empezar con una migración pendiente.
- **Sí:** el histórico solo por `GET /projects/{slug}`, pedido desde el navegador cuando la gráfica entra en pantalla (Andrés, 24 nov). **No:** el histórico en el HTML o en un JSON público. Saltaría el límite de 40 fichas al día por IP del SPEC 10 y lo prohíben los términos de uso.
- **Sí:** TanStack Query sin reintentos ante `429` y sin recarga al volver a la pestaña. **No:** sus valores por defecto (3 reintentos y recarga al enfocar). Cada petición cuenta contra el límite por IP del usuario; los valores por defecto lo gastarían solos.
- **Sí:** una regla de vigencia de tipologías en el frontend. **No:** tomar `latest_price` como precio de hoy. Una tipología agotada conserva su último precio, y el "desde" saltaría hacia abajo con un precio que ya no existe.
- **Sí:** un catálogo ficticio propio del frontend. **No:** reusar el de las evals del asesor, como proponía la *Propuesta curada*. Le faltan los casos raros, y cambiarlo movería el golden set del asesor.
- **Sí:** exportar el contrato desde el código con un test que lo compara. **No:** bajar `/openapi.json` de la API desplegada, que está apagado en producción desde el SPEC 10.
- **Sí:** CORS con orígenes explícitos y `Retry-After` expuesto. **No:** `*`. Sin `expose_headers`, el navegador no puede leer la hora del `429` aunque la API la mande.
- **Sí:** CSP nativa de Astro, aplicada desde el primer día. **No:** CSP en modo solo reporte con `_headers`, como decía la *Propuesta curada*. Sin despliegue no hay quién sirva esas cabeceras, y una política en `<meta>` no puede reportar. El modo reporte y `frame-ancestors` van con el SPEC 12.
- **Sí:** imagen por defecto en SVG propio con los colores del kit (Andrés, 24 nov). **No:** fotos del kit. Mostrarían casas que no son el proyecto, y su licencia no está confirmada (la descarga no trae créditos). Google Flow queda como opción para una ilustración en el mismo estilo, nunca para una foto realista.
- **Sí:** el kit Estatery tal cual, con solo los cambios necesarios (Andrés, 24 nov): morado `#685DE8` en lugar de `#7065F0` (4,86:1 frente a 4,37:1), gris sólido `#666B7F` en lugar del negro al 50 % (5,28:1 frente a 3,72:1), "desde" en lugar de "/month", la insignia POPULAR con la variación de precio, contenido real en lugar de testimonios y calificaciones, y marca propia. **No:** la paleta "Atardecer marino" (muy oscura y lejos del kit), ni las reglas de la *Propuesta curada* que contradicen el kit.
- **Sí:** recursos del kit desde un repo privado como submódulo. **No:** ponerlos en el repo público. La licencia de UI8 prohíbe redistribuir el kit con sus archivos fuente; en el sitio publicado sí se pueden usar, porque es el producto final.
- **No:** página "Cómo obtenemos los datos" (Andrés, 24 nov). Podría revelar secretos del negocio. La ficha enlaza al sitio de la constructora y los términos de uso siguen publicados.
- **Sí:** tuteo en todo el sitio (Andrés, 24 nov).
- **Sí:** un script propio para los tokens. **No:** Style Dictionary. Son unos 80 tokens y una sola salida; una dependencia más no se justifica. Se reconsidera si aparecen el modo oscuro o una app móvil.
- **Sí:** pnpm. **No:** npm. pnpm no ejecuta scripts de instalación de dependencias desde la versión 10 y puede esperar un día antes de instalar una versión nueva (`minimumReleaseAge`). Es la misma postura de cadena de suministro del SPEC 10.
- **Sí:** capturas de referencia generadas en Linux con la imagen oficial de Playwright. **No:** generarlas en el Mac. Las fuentes se dibujan distinto en cada sistema y CI fallaría siempre.
- **Sí:** listado sin filtros ni mapa. Con 49 proyectos, una cuadrícula ordenada por precio sirve hasta 11b.
- **No:** previews en Cloudflare en este spec. Andrés no respondió la pregunta; se asume que pasan al SPEC 12, porque la API no está en internet y la gráfica no tendría de dónde leer.
- **No:** logo y precarga en este spec. La precarga anima el logo, y el logo no está diseñado. Van juntos en un spec propio.
- **No:** datos estructurados JSON-LD de inmuebles. Las políticas de resultados enriquecidos de Google para inmuebles y ofertas no están verificadas, y un precio "desde" mal marcado sería engañoso.
- **No:** exponer `change_since_first_cop` en la API para mostrar "+$35 millones". Cambia el contrato por algo que no está en las pantallas aprobadas. Se reconsidera en 11b con el comparador.

## Riesgos identificados

| Riesgo | Mitigación |
| --- | --- |
| La frontera entre islas y HTML estático confunde al implementar | Una sola isla en este spec. Plan B escrito en la *Propuesta curada*: React Router v8 en modo framework |
| Recharts pesa demasiado en celulares de gama media | Isla con `client:visible`; tope de 250 KB medido en el PR; si no cabe, gráfica SVG propia (una línea escalonada son pocas decenas de líneas) |
| `shadcn init` o Tailwind v4 cambian su integración con Astro 7 | Fijar versiones en el lockfile; los componentes son código copiado y se ajustan a mano |
| La CSP en `<meta>` choca con `<ClientRouter />`, que el 11c necesita para que el asesor sobreviva a la navegación | Este spec no usa `<ClientRouter />`. El 11c decide: cabeceras desde Cloudflare (SPEC 12) o página dedicada del asesor |
| El token del repo privado vence o falta y el sitio sale con iconos de reemplazo sin que nadie lo note | Token de solo lectura con vencimiento anotado en `docs/deploy.md`; las capturas de Playwright se generan con los iconos del kit y fallan si cambian |
| Las capturas fallan por diferencias mínimas | Imagen de Playwright fija, fuente servida desde el sitio, fechas fijas en el catálogo y tolerancia baja (`maxDiffPixelRatio` 0,01) |
| El catálogo ficticio se desalinea del esquema | Lo valida `seed_schema.py` en cada corrida de CI |
| Un visitante que mira muchas fichas agota su límite diario de detalle | Mensaje con la hora de `Retry-After`; precio y tipologías siguen en el HTML |
| La regla de vigencia falla si un día el scraper lee solo una parte de las tipologías de un proyecto | La ficha muestra la fecha de cada precio. Si pasa en producción, se corrige en el scraper, no en el frontend |

## Lo que **no** entra en este spec

- Búsqueda con filtros, mapa, dibujar zona, comparador, calculadoras y "¿Me alcanza?" (11b).
- Asesor en la web (11c).
- Logo y precarga.
- Fotos reales de los proyectos.
- Despliegue, previews, dominio, cabeceras de seguridad, Turnstile y analítica (SPEC 12).
- Versión en inglés y modo oscuro.

Cada uno, si llega, va en su propio spec.
