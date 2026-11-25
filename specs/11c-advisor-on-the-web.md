# SPEC 11c — Asesor en la web

> **Estado:** aprobado
> **Depende de:** SPEC 08, SPEC 10, SPEC 11b
> **Fecha:** 2026-11-25
> **Objetivo:** Poner el asesor en la página `/asesor/` del sitio, calcada de la pantalla *Message* del kit Estatery, con los pasos de cada respuesta en vivo por SSE, tarjetas de los proyectos que menciona y las conversaciones guardadas en el navegador.

## Por qué existe este spec

El asesor responde desde el SPEC 08, pero solo con `curl` o la terminal (`docs/advisor.md`, sección "Run"). En la web no existe: el inicio esconde la ventaja "Asesor con fuentes" hasta este spec (`web/src/pages/index.astro:26-27`) y la navegación no lo enlaza (`web/src/components/SiteHeader.astro:21-28`). Es la mitad "IA" del producto y del portafolio.

Decisiones de Andrés del 25 nov que este spec aplica:

- El asesor vive en una **página propia, `/asesor/`**, calcada de *Message* del kit: conversaciones a la izquierda, chat al centro y el proyecto en contexto a la derecha. La ficha lo abre con su proyecto ya cargado.
- Mientras responde, se ven **los pasos en vivo** ("Buscando proyectos…") y al final llega la **respuesta ya verificada**. No se muestra el texto palabra por palabra.
- El navegador guarda **la lista de conversaciones**, que se borran solas a los 7 días sin actividad, como en el servidor. La persona puede **desactivar ese borrado** y conservar su historial.
- Cuando la respuesta menciona proyectos, se muestran **tarjetas pequeñas del kit** con enlace a la ficha.

Fuentes:

- Pantallas del kit: *Message* (lista de conversaciones, burbujas, compositor y panel derecho con el inmueble), *Message - Empty State* y, en móvil, *Message* y *Message - Details*.
- Cuaderno C3-P4 (asesor): copiloto junto a la vista estructurada, 3 a 5 preguntas sugeridas, botón "Nueva consulta", fuente visible, tarjeta útil ante el límite, aviso de que no es asesoría financiera.
- Cuaderno C5-P2 (interfaz del asesor): interfaz propia con shadcn/ui sobre SSE directo (`fetch` y `ReadableStream`), sin CopilotKit ni Vercel AI SDK; Markdown sin HTML crudo y con esquemas de URL validados; `role="alert"` en los errores.
- *Propuesta curada del frontend (SPEC 11)*, sección "Asesor (11c)" y §7 (cambios de backend).

Estado actual del repo (`main` en `4933ef4`):

- `src/sobreplano/interface/api/routes/advisor.py:42-67`: `POST /advisor/chat` responde JSON con `thread_id`, `reply` y `tools_used`, después de terminar todo el turno. No hay streaming.
- `src/sobreplano/infrastructure/advisor/langgraph_advisor.py:83-173`: `LangGraphAdvisor.reply` corre el grafo con `graph.invoke` y aplica después la redacción y la verificación de cifras (`:153-163`) sobre la respuesta completa. Por eso el texto no puede salir palabra por palabra sin saltarse esas protecciones.
- `src/sobreplano/infrastructure/advisor/langgraph_advisor.py:105-117`: la configuración del grafo ya admite `callbacks` de LangChain. Por ahí se pueden avisar los pasos sin tocar el grafo.
- `src/sobreplano/domain/ports.py:117-127`: el puerto `AdvisorAgent` solo tiene `reply(thread_id, message)`.
- `src/sobreplano/application/ask_advisor.py:33-65`: `AskAdvisor` revisa el presupuesto, la conversación y el límite de 20 mensajes antes de llamar al agente, y registra el gasto.
- `src/sobreplano/domain/advisor.py:38-47`: `AdvisorReply` trae `tool_calls` con los argumentos y la salida de cada herramienta, pero no dice qué proyectos menciona la respuesta.
- `src/sobreplano/infrastructure/advisor/tool_schemas.py:158-162` y `:261-265`: las salidas de `search_projects`, `get_project` y `compare_projects` traen `slug` y nombre de cada proyecto.
- `src/sobreplano/interface/api/rate_limit.py:97-132`: `RateLimiter.check` cuenta la petición y lanza `429` con `Retry-After`, pero no devuelve cuántos mensajes le quedan al cliente. `:154-161`: el asesor tiene su propio grupo (5 por minuto, 30 al día, falla cerrado).
- `src/sobreplano/interface/api/main.py:55-64`: CORS solo permite `GET`; el comentario ya dice que el `POST` del asesor entra en el 11c.
- `web/astro.config.mjs:37`: la CSP ya permite el origen de la API en `connect-src`.
- `web/src/lib/api/client.ts:34-37`: el navegador lee la API desde `PUBLIC_API_URL`.
- `web/src/lib/projects.ts:42`: cada `ProjectView` trae `sourceUrl`, la ficha del proyecto en el sitio de la constructora.
- `web/src/components/PriceCard.astro:65-74`: la ficha solo tiene el botón "Ver en el sitio de {constructora}".
- `uv.lock`: FastAPI 0.162, que trae `EventSourceResponse` desde la 0.135, y LangGraph 1.2.
- Riesgo que dejó el 11a: la CSP en `<meta>` choca con `<ClientRouter />`. Una página propia no necesita `<ClientRouter />`, así que el choque desaparece.

## Alcance

**Dentro:**

- **Backend:**
  - `POST /advisor/chat/stream`, con SSE, que avisa cada herramienta al empezar y al terminar y cierra con la respuesta verificada. `POST /advisor/chat` sigue igual (terminal, `curl`, evals).
  - Los proyectos mencionados en cada respuesta (`projects`, lista de slugs), en el endpoint nuevo y en el actual.
  - Cuántos mensajes le quedan hoy al cliente (`remaining_today`) en la respuesta final del endpoint nuevo.
  - CORS con `POST` y la cabecera `Content-Type`.
- **Página `/asesor/`** como isla de React (`client:load`), calcada de *Message* del kit:
  - columna izquierda: "Tus conversaciones", buscador de conversaciones y botón "Nueva consulta";
  - centro: el hilo con burbujas del kit, los pasos de cada respuesta, el Markdown de la respuesta, las tarjetas de proyectos y el compositor;
  - columna derecha: el proyecto en contexto o, si no hay, los proyectos mencionados en la conversación;
  - estado vacío con preguntas sugeridas (3 a 5);
  - el aviso fijo bajo el compositor.
- **Contexto desde la ficha:** botón suave "Pregúntale al asesor" en la ficha, que abre `/asesor/?proyecto={slug}` con el proyecto en el panel derecho y preguntas sugeridas sobre él.
- **Conversaciones en el navegador** (`localStorage`): lista, borrado automático a los 7 días sin actividad, interruptor "Conservar mis conversaciones en este navegador" y botón "Borrar mis conversaciones".
- **Estados:** esperando, pasos en vivo, respuesta, `429` por minuto y por día, presupuesto agotado, asesor no disponible, conversación llena (`409`), conversación que ya no existe (`404`), error de red y pérdida de conexión a mitad de la respuesta.
- **Markdown seguro:** sin HTML crudo ni imágenes; enlaces solo a fichas del sitio y a los dominios de las constructoras del catálogo.
- **Móvil:** el hilo a pantalla completa, la lista de conversaciones y el proyecto en contexto como hojas (*Message* y *Message - Details* del kit).
- **Entradas:** "Asesor" en la navegación, la cuarta ventaja del inicio ("Asesor con fuentes") y el botón de la ficha.
- **Pruebas:** pytest del endpoint, del aviso de pasos y de los proyectos mencionados, con agentes falsos; Vitest de la lógica del cliente; Playwright con la API simulada por `page.route`, axe, capturas y Lighthouse. Ninguna prueba llama al modelo.
- **Documentación:** `docs/advisor.md`, `docs/frontend.md`, `web/DESIGN.md`, `docs/security.md`, `docs/terms-of-use.md` y `CLAUDE.md`.

**Fuera (para specs futuros):**

- Texto palabra por palabra. Necesitaría verificar cifras sobre texto parcial (ver Decisiones).
- Un panel del asesor sobre otras páginas, como la búsqueda o la ficha, que sobreviva a la navegación.
- Borrar una conversación del servidor desde la web (`DELETE /advisor/threads/{id}`). Hoy se borra sola a los 7 días.
- Recuperar una conversación desde el servidor (`GET /advisor/threads/{id}`). El historial vive en el navegador.
- Cuentas, conversaciones sincronizadas entre dispositivos y voz.
- Que el asesor aplique filtros en la búsqueda o mueva el mapa.
- Calculadoras y comparador en la web (siguen pendientes desde el 11b).
- Turnstile, despliegue de la API con streaming y la limpieza programada de conversaciones (SPEC 12).

## Modelo de datos

La base de datos no cambia. Cambian dos tipos del dominio, el puerto del agente, el contrato de la API y aparece el almacenamiento del navegador.

### 1. Dominio y puerto

```python
@dataclass(frozen=True)
class AdvisorStep:
    """One tool of a turn starting or ending, for the live progress of the web."""

    tool: str  # name of the tool, as in tools_used
    phase: Literal["start", "end"]


@dataclass(frozen=True)
class AdvisorReply:
    ...  # fields of today, unchanged
    projects: list[str] = field(default_factory=list[str])  # slugs the answer names, in order


class AdvisorAgent(Protocol):
    def reply(
        self, thread_id: UUID, message: str, on_step: Callable[[AdvisorStep], None] | None = None
    ) -> AdvisorReply: ...
```

- `on_step` es opcional. La terminal, `POST /advisor/chat` y las evals no lo pasan y se comportan como hoy.
- `LangGraphAdvisor.reply` agrega a `callbacks` un manejador de LangChain (`on_tool_start` y `on_tool_end`) que llama a `on_step`. El grafo no cambia.
- `AskAdvisor` suma `check(thread_id, today)`, solo de lectura, con las mismas comprobaciones y excepciones que hoy (presupuesto, conversación inexistente, límite de 20 mensajes). `__call__` recibe `on_step` y lo pasa al agente.

### 2. Proyectos mencionados

`mentioned_projects(text, tool_calls)` en `src/sobreplano/infrastructure/advisor/mentions.py`:

- reúne los pares slug y nombre de las salidas de `search_projects`, `get_project` y `compare_projects` del turno;
- se queda con los que tienen el nombre en la respuesta, sin importar tildes ni mayúsculas;
- los ordena por su primera aparición en el texto y devuelve como máximo 6, el mismo tope de `MAX_DETAILS_PER_MESSAGE`;
- ignora salidas que no son JSON válido, como los errores de herramienta.

Se calcula sobre el texto final, después de la redacción y la verificación de cifras. Si la respuesta es el texto fijo de "no pude verificar", la lista queda vacía.

### 3. `POST /advisor/chat/stream`

Entrada: la misma de `POST /advisor/chat` (`message` de 1 a 1.000 caracteres y `thread_id` opcional).

Antes de abrir el flujo, la respuesta sale como HTTP normal, con el mismo `detail` de hoy:

| Caso | Código |
| --- | --- |
| Mensaje vacío o de más de 1.000 caracteres | `422` |
| Límite por minuto o por día | `429` con `Retry-After` |
| Contadores caídos | `503` |
| Presupuesto del día agotado | `503` (`advisor budget exhausted for today`) |
| Conversación inexistente o borrada | `404` |
| Conversación con 20 mensajes | `409` |

Esas comprobaciones corren en dependencias de FastAPI (`AdvisorRateLimitDep` y una nueva, `AdvisorTurnCheckDep`, que llama a `AskAdvisor.check`), porque un `HTTPException` lanzado dentro del generador llegaría con el flujo ya abierto y el código `200`.

Con todo en orden, la respuesta es `text/event-stream` con estos eventos:

| Evento | `data` (JSON) | Cuándo |
| --- | --- | --- |
| `step` | `{"tool": "search_projects", "phase": "start"}` | Al empezar cada herramienta |
| `step` | `{"tool": "search_projects", "phase": "end"}` | Al terminar cada herramienta |
| `answer` | `{"thread_id": "…", "reply": "…", "tools_used": […], "projects": ["slug"], "remaining_today": 27}` | Una vez, al final |
| `error` | `{"status": 503, "detail": "advisor could not answer"}` | Si el turno falla después de abrir el flujo (demasiadas rondas de herramientas o el proveedor caído) |

- FastAPI manda un comentario `ping` cada 15 s sin eventos, `Cache-Control: no-cache` y `X-Accel-Buffering: no`.
- El turno corre en un hilo aparte y el generador lee sus eventos de una cola. El endpoint es `def`, como manda `CLAUDE.md`.
- El generador abre su propia sesión desde `app.state.session_factory` y hace `commit` al final, también después de `AdvisorLimitError`, para que el gasto quede registrado, igual que `routes/advisor.py:61-64`.
- `remaining_today` es `30 − mensajes contados hoy`. Sale de `RateLimiter.check`, que ahora devuelve los conteos de la ventana (`Remaining`), o `null` si los límites están apagados.
- Si el navegador se desconecta, el turno termina igual y queda en la conversación y en `llm_usage`.

`POST /advisor/chat` agrega `projects` a `ChatOut`. Es un campo nuevo, así que los clientes actuales siguen funcionando. `openapi.json` se regenera con `export_openapi`.

### 4. Conversaciones en el navegador

Clave `sobreplano.asesor.v1` en `localStorage`:

```ts
type StoredMessage =
  | { role: "user"; text: string; at: string }
  | { role: "advisor"; text: string; tools: string[]; projects: string[]; at: string };

type StoredConversation = {
  id: string;               // thread_id del servidor
  title: string;            // la primera pregunta, hasta 60 caracteres
  projectSlug: string | null; // el proyecto en contexto, si se abrió desde una ficha
  messages: StoredMessage[];
  updatedAt: string;        // ISO, para el borrado y el orden
  closed: boolean;          // true si el servidor ya no la tiene (404) o llegó a 20 mensajes
};

type AdvisorStore = {
  keepHistory: boolean;     // false por defecto: borrado a los 7 días sin actividad
  conversations: StoredConversation[];   // de la más reciente a la más vieja, hasta 30
};
```

- Al abrir la página, si `keepHistory` es `false`, se borran las conversaciones con `updatedAt` de hace más de 7 días.
- Con `keepHistory` en `true` se conservan en el navegador. El servidor igual las borra a los 7 días sin actividad: se pueden leer, pero al escribir en una de ellas la API responde `404`, la conversación queda `closed` y la pregunta sigue en una conversación nueva, con un aviso.
- Tope de 30 conversaciones: al pasar, se borra la más vieja y se avisa.
- Si `localStorage` no existe o está lleno (modo privado, cuota), la página funciona igual, solo con la conversación actual en memoria, y lo dice.
- "Borrar mis conversaciones" vacía la clave. El texto aclara que en el servidor se borran solas a los 7 días sin actividad.
- Nada de esto sale del navegador. No va en la URL, salvo `proyecto`.

### 5. URL de la página

| Parámetro | Ejemplo | Regla |
| --- | --- | --- |
| `proyecto` | `proyecto=arrayanes-del-sur` | Slug de un proyecto del catálogo del build; uno desconocido se ignora |
| `c` | `c=6f1c…` | `thread_id` de una conversación guardada; una desconocida se ignora |

### 6. Textos fijos

**Pasos** (`web/src/lib/advisor/labels.ts`):

| Herramienta | Mientras corre | En el resumen |
| --- | --- | --- |
| `search_projects` | Buscando proyectos… | Buscó proyectos |
| `get_project` | Revisando el proyecto… | Revisó un proyecto |
| `compare_projects` | Comparando proyectos… | Comparó proyectos |
| `list_developers` | Revisando constructoras… | Revisó constructoras |
| `simulate_mortgage` | Simulando el crédito… | Simuló el crédito |
| `max_affordable_price` | Calculando cuánto puedes comprar… | Calculó cuánto puedes comprar |
| `down_payment_plan` | Calculando la cuota inicial… | Calculó la cuota inicial |
| otra | Consultando datos… | Consultó datos |

Antes del primer paso: "Pensando…".

**Preguntas sugeridas** (`web/src/lib/advisor/suggestions.ts`):

- Sin proyecto: "¿Qué proyectos hay en Itagüí por menos de 300 millones?", "¿Cuáles proyectos han subido más desde que los siguen?", "Compara los dos proyectos más baratos de Envigado", "Gano 6 millones y tengo 40 ahorrados, ¿qué puedo comprar?".
- Con proyecto: "¿Cuánto ha subido {nombre}?", "¿Cuánto pagaría al mes de cuota inicial en {nombre}?", "Compara {nombre} con otros proyectos de {municipio}".

**Aviso bajo el compositor:** "Respondo con los precios que publican las constructoras. No es asesoría financiera ni una oferta. No escribas datos personales." Lleva un enlace a los términos de uso.

**Errores:**

| Caso | Texto | Acción |
| --- | --- | --- |
| `429`, `Retry-After` de 60 s o menos | "Vas muy rápido. Podrás preguntar de nuevo en {n} segundos." | El envío se activa solo al terminar la cuenta |
| `429`, `Retry-After` de más de 60 s | "Llegaste al límite de preguntas de hoy. Podrás seguir a las {hora}." | Enlace "Seguir con la búsqueda" (`/proyectos/`) |
| `503`, presupuesto agotado | "El asesor ya respondió todo lo que podía hoy. Vuelve mañana; la búsqueda sigue funcionando." | Enlace a `/proyectos/` |
| `503`, otro motivo, o evento `error` | "No pude responder esta vez." | Botón "Reintentar", que reenvía la misma pregunta |
| `409` | "Esta conversación llegó a 20 mensajes." | Botón "Nueva consulta" con la pregunta ya escrita |
| `404` | "Esta conversación ya no existe en el servidor. Tu pregunta va en una conversación nueva." | Sigue sola en una conversación nueva |
| Red o flujo cortado | "Se perdió la conexión antes de la respuesta." | Botón "Reintentar". Advierte que la pregunta pudo haberse contado |

Los errores van en `role="alert"`. Ninguno muestra trazas ni el `detail` en inglés de la API.

**Contador:** después de cada respuesta, "Te quedan {n} preguntas hoy" junto al compositor, solo si `remaining_today` llega y es 10 o menos.

## Plan de implementación

1. **Dominio y agente.**
   - `AdvisorStep` y `AdvisorReply.projects` en `domain/advisor.py`; `on_step` en `AdvisorAgent` (`domain/ports.py`).
   - `StepCallback` en `infrastructure/advisor/` y `on_step` en `LangGraphAdvisor.reply`.
   - `mentions.py` con `mentioned_projects`.
   - `AskAdvisor.check` y `on_step` en `AskAdvisor.__call__`.
   - Tests: el agente con un modelo falso que llama a dos herramientas emite `start` y `end` de cada una en orden; sin `on_step` la respuesta es idéntica a la de hoy; `mentioned_projects` con nombres con tildes, repetidos, sin mención, salida de error y más de 6 proyectos; `check` con cada excepción.

   Commit `feat:`.
2. **Endpoint con SSE.**
   - `RateLimiter.check` devuelve `Remaining` (conteos de minuto y día), y `AdvisorRateLimitDep` lo expone.
   - `AdvisorTurnCheckDep` y `POST /advisor/chat/stream` en `routes/advisor.py`, con `response_class=EventSourceResponse`, hilo de trabajo, cola y sesión propia.
   - `projects` en `ChatOut`.
   - CORS: `allow_methods=["GET", "POST"]` y `allow_headers=["Content-Type"]`.
   - `export_openapi` y la instantánea de `openapi.json`.
   - Tests en `tests/unit/interface/test_advisor_stream.py`: orden de eventos con un `AskAdvisor` falso; `422`, `429`, `404`, `409` y `503` de presupuesto como códigos HTTP antes del flujo; `error` con `503` cuando el turno lanza `AdvisorLimitError`, con el gasto confirmado; `remaining_today`. En `test_cors.py`: el `OPTIONS` previo de un `POST` desde el origen permitido pasa sin contar contra el límite, y desde otro origen no trae `access-control-allow-origin`. En `tests/integration/`, un turno por el endpoint nuevo con un agente falso deja la conversación y su conteo en la base.

   Commit `feat:`.
3. **Cliente del asesor** (`web/src/lib/advisor/`).
   - `stream.ts`: `fetch` con `POST`, lee el cuerpo con `ReadableStream` y `eventsource-parser`, valida cada evento y traduce los códigos HTTP a los errores de la sección 6. Una sola petición en curso.
   - `store.ts`: lectura y escritura de `localStorage` con versión, borrado a los 7 días, tope de 30, `keepHistory` y modo sin almacenamiento.
   - `links.ts`: permite rutas `/proyectos/{slug}/` y `https://` a los dominios de `sourceUrl` del catálogo; cualquier otro enlace queda como texto.
   - `labels.ts` y `suggestions.ts`.
   - Tests de Vitest para los cuatro módulos, incluidos un flujo cortado, un evento desconocido (se ignora), un JSON inválido (error), `localStorage` lleno y el cambio de día con conversaciones viejas.

   Commit `feat:`.
4. **Página `/asesor/`.**
   - `web/src/pages/asesor/index.astro` monta `AdvisorPage` con los `SearchItem` del catálogo (para las tarjetas y el panel), los dominios permitidos y las preguntas sugeridas.
   - Componentes en `web/src/components/advisor/`: `AdvisorPage`, `ConversationList`, `Thread` (con `role="log"`), `Bubble`, `StepTrace`, `AnswerMarkdown` (`react-markdown` y `remark-gfm`, sin HTML crudo ni imágenes, enlaces por `links.ts`), `Composer` (Enter envía, Mayús+Enter salta de línea, contador de 1.000 caracteres, botón desactivado mientras responde), `ProjectPanel` y `Suggestions`.
   - La tarjeta S del kit como variante `size="sm"` de `ProjectCard.tsx`. Una tarjeta solo aparece si su slug está en el catálogo del build.
   - Móvil (< 1024 px): hilo a pantalla completa; "Tus conversaciones" y el proyecto en contexto en hojas (`sheet` de shadcn) que se abren desde la barra superior del hilo.
   - El foco va al compositor al cargar y vuelve a él después de cada respuesta. Los pasos se anuncian con `aria-live="polite"`.

   Commit `feat:`.
5. **Entradas al asesor.** "Asesor" en `SiteHeader.astro`, en escritorio y en el menú móvil; la cuarta ventaja en `index.astro`; el botón suave "Pregúntale al asesor" en `PriceCard.astro`, que lleva a `/asesor/?proyecto={slug}`. Sin JavaScript nuevo en esas páginas. Las capturas que cambian se regeneran en Linux. Commit `feat:`.
6. **Pruebas de navegador.**
   - `web/tests/e2e/advisor.spec.ts`, con `page.route` simulando `POST /advisor/chat/stream` con cuerpos SSE fijos: estado vacío y pregunta sugerida; pasos en vivo y respuesta con tabla, enlace permitido, enlace no permitido (queda como texto) y dos tarjetas; segundo mensaje en la misma conversación; recargar y ver la conversación; abrir desde una ficha con su proyecto; `429` de minuto con la cuenta regresiva; `429` de día; `503` de presupuesto; `409`; `404` que sigue en una conversación nueva; flujo cortado; borrado a los 7 días con el reloj de Playwright; interruptor de conservar; "Borrar mis conversaciones"; móvil con las dos hojas.
   - axe sobre `/asesor/` vacía, con conversación, con un error y con cada hoja abierta, a 390 y 1440 px.
   - Capturas a 390 y 1440 px, vacía y con conversación.
   - Lighthouse sobre `/asesor/`.

   Commit `test:`.
7. **Documentación.**
   - `docs/advisor.md`: el endpoint nuevo, sus eventos, `projects`, `remaining_today` y el manejador de pasos.
   - `docs/frontend.md`: la página, el almacenamiento, los enlaces permitidos y cómo se prueba sin la API.
   - `web/DESIGN.md`: burbujas, pasos, tarjeta S, panel derecho y aviso.
   - `docs/security.md`: CORS con `POST`, los enlaces de las respuestas como entrada no confiable y las conversaciones en el navegador.
   - `docs/terms-of-use.md`, punto 6 en los dos idiomas: las conversaciones se guardan en el navegador y cómo borrarlas.
   - `CLAUDE.md`: la ruta nueva y la línea de estado.

   Commit `docs:`.

Ningún paso tiene llamadas pagas ni cuentas nuevas. La única dependencia nueva de Python es ninguna; en `web/` entran `react-markdown`, `remark-gfm` y `eventsource-parser`.

## Criterios de aceptación

Cada criterio se verifica pegando el comando y su salida en el PR (constitución, principio 6).

- [ ] `uv run pytest -m "not integration"`, `uv run ruff check`, `uv run ruff format --check`, `uv run pyright` y `uv run lint-imports` pasan, incluidos los tests nuevos de los pasos 1 y 2.
- [ ] `uv run --env-file .env pytest tests/integration` pasa, incluido el turno por el endpoint nuevo.
- [ ] `uv run python -m sobreplano.interface.cli.export_openapi --check` sale con 0 después de regenerar el contrato.
- [ ] Con la API local y un agente falso, `curl -N -X POST localhost:8000/advisor/chat/stream -H 'content-type: application/json' -d '{"message":"hola"}'` muestra eventos `step` y un `answer` con `thread_id`, `projects` y `remaining_today`.
- [ ] Con el presupuesto del día agotado, el mismo `curl -i` responde `HTTP/1.1 503` y no `200` con el flujo abierto. Lo mismo con un `thread_id` inexistente (`404`) y con una conversación de 20 mensajes (`409`).
- [ ] Con `CORS_ALLOWED_ORIGINS='["http://localhost:4321"]'`, el `OPTIONS` previo de un `POST` desde ese origen trae `access-control-allow-origin` y `access-control-allow-methods` con `POST`, y no suma al contador del asesor.
- [ ] Sin `on_step`, `LangGraphAdvisor.reply` devuelve lo mismo que antes del spec para los casos de `tests/unit/infrastructure/test_langgraph_advisor.py`, que siguen pasando sin cambios.
- [ ] `pnpm --dir web test`, `pnpm --dir web check`, `pnpm --dir web rules` y `pnpm --dir web tokens && git diff --exit-code web/src/styles/tokens.css` pasan.
- [ ] En `/asesor/`, una pregunta sugerida muestra "Pensando…", los pasos en vivo, la respuesta con su tabla y dos tarjetas S con enlace a la ficha (Playwright con la API simulada).
- [ ] Un enlace de la respuesta a un dominio que no es de ninguna constructora del catálogo se ve como texto, sin `<a>`; uno a la constructora abre en otra pestaña con `rel="noopener noreferrer"`.
- [ ] Una respuesta con `<script>` o `<img src=x onerror=…>` en el texto no crea ningún elemento `script` ni `img` en la página.
- [ ] Al recargar `/asesor/?c={id}` se ve la conversación completa, y la siguiente pregunta lleva su `thread_id`.
- [ ] Desde la ficha, "Pregúntale al asesor" abre `/asesor/?proyecto={slug}` con el proyecto en el panel derecho y las tres preguntas sugeridas con su nombre.
- [ ] Con el reloj de Playwright 8 días adelante, una conversación sin actividad desaparece. Con "Conservar mis conversaciones" encendido, sigue ahí. "Borrar mis conversaciones" vacía la lista.
- [ ] Con un `429` y `Retry-After: 20`, el envío queda desactivado con la cuenta regresiva y se activa al llegar a cero. Con `Retry-After: 3600`, se ve el texto del límite diario y el enlace a la búsqueda.
- [ ] Con un `503` de presupuesto, un `409` y un `404`, se ven los textos y acciones de la sección 6, en `role="alert"`.
- [ ] Con el flujo cortado después de un `step`, se ve "Se perdió la conexión antes de la respuesta." con "Reintentar", y el compositor vuelve a funcionar.
- [ ] Mientras una respuesta está en curso, el botón de enviar está desactivado y Enter no manda una segunda petición (Playwright cuenta una sola).
- [ ] `@axe-core/playwright` no reporta violaciones en `/asesor/` (vacía, con conversación, con error y con cada hoja abierta) a 390 y 1440 px.
- [ ] Con el teclado solo se llega a la lista de conversaciones, a las preguntas sugeridas, al compositor, a las tarjetas y al panel derecho, y el foco siempre se ve.
- [ ] Lighthouse CI (móvil) en `/asesor/`: rendimiento ≥ 0,90, accesibilidad = 1,00 y CLS ≤ 0,1. El PR anota el JavaScript inicial (gzip), que debe ser ≤ 150 KB.
- [ ] Ninguna página muestra mensajes `Content Security Policy` en la consola, y la CSP no cambia.
- [ ] Las capturas de `/asesor/` a 390 y 1440 px están aprobadas y el PR las muestra al lado de *Message* del kit. Las del inicio y la ficha que cambian por las entradas nuevas se regeneran en Linux.
- [ ] `grep -rl '"history"' web/dist` no devuelve nada.
- [ ] Los workflows `ci.yml` y `web.yml` quedan en verde en el PR.

## Decisiones tomadas y descartadas

- **Sí:** página propia `/asesor/`, calcada de *Message* del kit (Andrés, 25 nov). **No:** un panel sobre cada página. Para que sobreviva a la navegación necesita `<ClientRouter />`, que choca con la CSP en `<meta>` (riesgo del 11a), y sin él una respuesta en curso se pierde al cambiar de página. La ficha abre el asesor con su contexto, que es lo que pedía el cuaderno C3-P4.
- **Sí:** pasos en vivo y respuesta final (Andrés, 25 nov). **No:** texto palabra por palabra. La redacción y la verificación de cifras del SPEC 10 trabajan sobre la respuesta completa y a veces la reescriben (`langgraph_advisor.py:153-163`). Mostrar el texto antes dejaría ver cifras sin verificar y datos personales sin redactar. **No:** solo un indicador de espera, porque una espera de 3 a 10 s sin saber qué pasa invita a reenviar y gasta el cupo de 5 por minuto.
- **Sí:** los pasos con callbacks de LangChain en la configuración del grafo. **No:** `astream_events` ni cambiar el grafo a asíncrono. El grafo, las evals y la terminal siguen por el mismo camino, y `on_step` solo agrega avisos.
- **Sí:** endpoint nuevo y el actual intacto. La terminal, los ejemplos de `docs/advisor.md` y cualquier cliente JSON siguen funcionando.
- **Sí:** comprobaciones previas en dependencias, para que `404`, `409`, `429` y `503` salgan como códigos HTTP y no como eventos dentro de un `200`.
- **Sí:** `remaining_today` en el evento `answer`. **No:** cabeceras `RateLimit-*`. Habría que exponerlas en CORS y no las verían los errores dentro del flujo. Antes de la primera respuesta no hay contador.
- **Sí:** el contador solo con 10 o menos preguntas restantes. Mostrarlo siempre recuerda el límite a quien no está cerca de él.
- **Sí:** conversaciones en `localStorage` con borrado a los 7 días y la opción de conservarlas (Andrés, 25 nov). Una conversación conservada se puede leer aunque el servidor ya la haya borrado; para seguir, la pregunta va en una conversación nueva.
- **Sí:** tarjetas S del kit con los slugs que devuelve la API y los datos del catálogo del build (Andrés, 25 nov). **No:** mandar la tarjeta completa desde la API, que duplicaría el contrato del catálogo. Un proyecto que no está en el build no tiene ficha, así que no se pinta su tarjeta.
- **Sí:** proyectos mencionados por nombre en el texto final, con tope de 6. **No:** todos los que devolvieron las herramientas, que en una búsqueda amplia pueden ser 17 (`docs/advisor.md`, conversación 4) y no coinciden con lo que la respuesta dice.
- **Sí:** interfaz propia con shadcn/ui, `react-markdown`, `remark-gfm` y `eventsource-parser`. **No:** assistant-ui, CopilotKit ni Vercel AI SDK (cuaderno C5-P2). Las tres esperan otro protocolo o un servidor intermedio, y la página tiene un solo hilo sin edición ni ramas.
- **Sí:** enlaces solo a fichas del sitio y a los dominios de las constructoras del catálogo. Un texto de una página raspada podría colar un enlace a otro sitio por la respuesta del asesor (`docs/security.md`, sección de inyección). Las tablas sí se permiten, porque el asesor compara con tablas.
- **Sí:** sin botón "Detener". Detener en el navegador no detiene el turno en el servidor: se cobraría igual y la respuesta quedaría en la conversación sin que la persona la vea.
- **Sí:** el contexto del proyecto viaja en las preguntas sugeridas, con el nombre del proyecto. **No:** un campo de contexto en la API. El asesor ya busca por nombre (`search_projects`, regla 7 del prompt).
- **No:** Turnstile en este spec. Va con el despliegue (SPEC 12), igual que la alarma de `429`.

## Riesgos identificados

| Riesgo | Mitigación |
| --- | --- |
| La API desplegada no deja pasar SSE (API Gateway corta el flujo o lo guarda entero) | El SPEC 12 elige dónde corre la API sabiendo que necesita streaming. La web trata un flujo cortado como error con "Reintentar", y `POST /advisor/chat` sigue como respaldo |
| Un `HTTPException` dentro del generador llega con `200` | Las comprobaciones van en dependencias; un criterio de aceptación lo prueba con `curl -i` |
| La sesión de la petición se cierra antes de que termine el flujo | El generador abre y cierra su propia sesión, como `RateLimiter` (`main.py:32-35`) |
| El hilo de trabajo queda colgado si el proveedor no responde | Tiempo máximo del cliente del modelo (ya configurado en `chat_models.py`) y un `error` si el hilo no termina en 60 s |
| La persona cierra la pestaña a mitad de la respuesta | El turno se cobra y queda en el servidor. Al volver, la conversación muestra la pregunta sin respuesta y ofrece repetirla |
| `localStorage` lleno o bloqueado | Modo en memoria con aviso; tope de 30 conversaciones |
| El JavaScript de Markdown pesa en celulares | Presupuesto de 150 KB en los criterios; `react-markdown` con `React.memo` por mensaje |
| El nombre de un proyecto no aparece tal cual en la respuesta y su tarjeta no sale | Comparación sin tildes ni mayúsculas; si aun así falla, la respuesta conserva su enlace en el texto |
| Las evals cambian por el campo nuevo de `AdvisorReply` | `projects` tiene valor por defecto y las evals no lo leen; las pruebas del agente sin `on_step` siguen iguales |

## Lo que **no** entra en este spec

- Texto palabra por palabra.
- Panel del asesor sobre otras páginas.
- Borrar o recuperar conversaciones desde el servidor.
- Cuentas, sincronización entre dispositivos y voz.
- Que el asesor maneje filtros o el mapa.
- Calculadoras y comparador.
- Turnstile, despliegue con streaming y limpieza programada (SPEC 12).

Cada uno, si llega, va en su propio spec.
