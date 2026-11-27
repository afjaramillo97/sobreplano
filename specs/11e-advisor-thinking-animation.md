# SPEC 11e — Animación de espera del asesor

> **Estado:** implementado
> **Depende de:** SPEC 11c
> **Fecha:** 2026-11-26
> **Objetivo:** Mientras el asesor responde, mostrar tres bolas en una órbita que se inclina y gira con profundidad (la variante "giroscopio") y hacer destellar el texto de esa línea, para que la espera se perciba como trabajo en curso, sin perder accesibilidad ni la estabilidad de las capturas.

## Por qué existe este spec

Hoy, mientras el asesor responde, "Pensando…" y cada paso en curso llevan un punto quieto. Se dejó así a propósito en el 11c, para que nada se moviera con `prefers-reduced-motion`. El resultado es que la espera se siente detenida, sobre todo en los segundos antes del primer paso. Andrés pidió una animación que haga sentir que se está procesando la información, del tipo de la de Claude o del "escribiendo…" de WhatsApp.

Decisiones de Andrés del 26 nov que este spec aplica:

- Entre seis opciones (puntos que rebotan, puntos que laten, paso con brillo, casa que respira, barra indeterminada y puntos en órbita) eligió **puntos en órbita**.
- Pidió que las bolas **se movieran también en profundidad**, más parecido a la animación de Claude. Entre tres variantes con profundidad eligió **F2, "giroscopio"**: el anillo gira, se tambalea y rota su plano, a velocidad 1,0×.
- Pidió también **el destello del texto** junto a la animación, como en la vista "Con pasos: el terminado queda quieto": solo destella la línea en curso. Los pasos terminados quedan quietos, con su check y su texto en gris.

### Estado actual del repo
/
`main` en `cc12192`, con el 11d ya integrado:

- `web/src/components/advisor/StepTrace.tsx:20-24` muestra "Pensando…" con `Dot` hasta el primer paso. `:29-36` muestra cada paso con `Dot` mientras corre y con `check-outline` cuando termina. `:45-52` define `Dot`, un punto de 8 px en una caja de 16 px.
- `StepTrace.tsx:15` es una región `aria-live="polite"`. Lo que anuncia es el texto, no el punto (`aria-hidden="true"`).
- `web/src/lib/advisor/labels.ts:9` define `THINKING = "Pensando…"`, y las pruebas lo usan (`web/tests/unit/advisor-labels.test.ts:15` y `web/tests/e2e/advisor.spec.ts:150`).
- `web/playwright.config.ts:17` toma las capturas con `animations: "disabled"`, que congela las animaciones CSS pero no las de `requestAnimationFrame`. La captura del asesor está en `web/tests/e2e/visual.spec.ts:79`.
- La CSP no permite `'unsafe-inline'` en `style-src` (`web/src/components/ui/popover.tsx:3-4`). Los estilos asignados desde JavaScript con el CSSOM sí están permitidos.

## Alcance

**Dentro:**

- `web/src/components/advisor/ThinkingOrbit.tsx`: la animación "giroscopio", sin librerías.
- `StepTrace.tsx` la usa en "Pensando…" y en el paso en curso más reciente. Si hay varios pasos corriendo, los anteriores conservan el punto quieto, para no tener varios bucles a la vez.
- `web/src/components/advisor/ShimmerText.tsx`: el destello del texto de esa misma línea, solo con CSS.
- Movimiento reducido: la órbita en un cuadro fijo y el texto quieto en gris, que cambia solo si la persona cambia su preferencia.
- Pruebas de Vitest y Playwright, y la captura del asesor estable.
- `web/DESIGN.md`: los parámetros de la animación.

**Fuera:**

- Animaciones en otras partes del sitio (la búsqueda, la calculadora o la carga del mapa).
- Sonidos, vibración o cambios en lo que dicen los pasos.
- Una versión de la órbita con `@keyframes`, que no puede proyectar en perspectiva con una inclinación que cambia. El destello sí usa `@keyframes`.

## Modelo de datos

No cambian la API, la base de datos ni el almacenamiento del navegador.

### Parámetros de la animación

Cada bola recorre un círculo en 3D. El círculo se inclina sobre el eje X, se rota sobre el eje Z y se proyecta en perspectiva. Para la bola `i` (0, 1 y 2) en el tiempo `t`, en segundos:

```
a     = 4,2·t + i·2π/3                 // posición en la órbita
tilt  = (68° + 16°·sin(1,3·t))          // inclinación que se tambalea
roll  = 0,9·t                           // rotación del plano
x, y  = R·cos a, R·sin a
y2, z = y·cos tilt, y·sin tilt
xr    = x·cos roll − y2·sin roll
yr    = x·sin roll + y2·cos roll
k     = F / (F − z)                     // perspectiva
d     = (z/R + 1) / 2                   // 0 atrás, 1 adelante
transform = translate(xr·k, yr·k) scale(0,6 + 0,6·d)
opacity   = 0,35 + 0,65·d
z-index   = round(100·d)
```

| Parámetro | Valor |
| --- | --- |
| Caja | 24 px en `StepTrace`; la vista previa aprobada usaba 44 px |
| Radio `R` | 30 % de la caja (7,2 px) |
| Bola | 25 % de la caja (6 px), redonda, color `action` (`#685DE8`) |
| Perspectiva `F` | 5,4·R |
| Velocidad | 1,0×, la aprobada. Es una constante del componente, no una opción |
| Cuadro fijo | `t = 0,12 s`: dos bolas adelante a los lados y una atrás, con al menos 2 px entre ellas a 24 px (el instante más despejado de los primeros 2 s) |

### Reglas del componente

- Las tres bolas son `<span aria-hidden="true">` dentro de una caja con `role="presentation"`. Lo que oye un lector de pantalla no cambia.
- Los estilos de cada cuadro se asignan con `element.style` desde una referencia, nunca con el atributo `style` en el HTML, para cumplir la CSP.
- El bucle corre con `requestAnimationFrame` y mide el tiempo transcurrido, no los cuadros, así que la velocidad no depende de la pantalla.
- Con `prefers-reduced-motion: reduce` no arranca el bucle y dibuja el cuadro fijo. Escucha el `change` de esa consulta mientras está montado.
- El bucle se detiene al desmontar y cuando la pestaña queda oculta (`visibilitychange`), y retoma donde iba.

### Destello del texto

`ShimmerText` recibe el texto de la línea en curso ("Pensando…" o el `runningLabel` del paso):

- Una onda de color recorre las letras de izquierda a derecha: cada letra pasa del gris del texto (`text-secondary`, `#4D5369`) al morado `action` (`#685DE8`) y vuelve. Ciclo de 1,8 s, `ease-in-out`, color `action` en el 20 % del ciclo y de vuelta al gris en el 40 %.
- Cada letra arranca 60 ms después de la anterior. El retraso se asigna desde JavaScript con el CSSOM, igual que la órbita. Los `@keyframes` van en `web/src/styles/global.css`.
- **Contraste:** cambia el color y no la opacidad, así que el texto nunca baja de 4,5:1 sobre el blanco de la tarjeta (`#685DE8` da 4,86:1). La opción C de la primera ronda desvanecía las letras y perdía contraste.
- **Accesibilidad:**
  - cada letra es un `<span aria-hidden="true">`, y el texto completo va en un `<span class="sr-only">`;
  - la región en vivo de `StepTrace` sigue anunciando "Pensando…" y cada paso de corrido, no letra por letra.
- **Cortes de línea:** las letras se agrupan por palabra en un `<span>` con `white-space: nowrap`, para que un paso largo baje de línea entre palabras y no a mitad de una.
- **Movimiento reducido:** sin animación, todo el texto en `text-secondary`.
- **Qué línea destella:** solo la que lleva la órbita, que es "Pensando…" o el último paso en curso. Al terminar el paso, la línea pasa a `doneLabel` con su check y deja de destellar.

## Plan de implementación

1. **Componente.** `ThinkingOrbit.tsx`, con su docstring de una línea, y la función pura `orbitFrame(t, size)`, que devuelve `transform`, `opacity` y `zIndex` de cada bola. Test de Vitest `web/tests/unit/thinking-orbit.test.ts`:
   - `orbitFrame(0, 24)` y `orbitFrame(1, 24)` contra valores calculados a mano;
   - la bola de adelante tiene la mayor escala y opacidad;
   - con movimiento reducido no se pide ningún cuadro;
   - al desmontar se cancela el cuadro pendiente;
   - con la pestaña oculta se detiene.

   `ShimmerText` y su test `web/tests/unit/shimmer-text.test.ts`:
   - el texto completo queda en el `sr-only`;
   - cada letra está en un `span` oculto, con su retraso de 60 ms;
   - las palabras quedan agrupadas.

   Commit `feat:`.
2. **Uso en `StepTrace`.** `ThinkingOrbit` en lugar de `Dot`, y `ShimmerText` en lugar del texto plano, en "Pensando…" y en el último paso en curso. La caja de la línea pasa de 16 a 24 px, sin cambiar la altura de la tarjeta más de 8 px. El check de "hecho" y los textos no cambian. Commit `feat:`.
3. **Pruebas de navegador.**
   - Playwright con la respuesta simulada que ya usa `advisor.spec.ts`:
     - con `reducedMotion: "no-preference"`, la posición de una bola cambia entre dos lecturas separadas 200 ms;
     - con `reducedMotion: "reduce"`, la posición no cambia;
     - con `reducedMotion: "reduce"`, las letras de `ShimmerText` tienen `animation-name: none`.
   - `visual.spec.ts` abre el asesor con `reducedMotion: "reduce"`, y una captura nueva del estado "Pensando…" a 390 y 1440 px, regenerada en Linux.
   - axe sin violaciones en `/asesor/` con la animación visible.

   Commit `test:`.
4. **Documentación.** `web/DESIGN.md`: la órbita y el destello, sus parámetros, el estado quieto y por qué no se usa la chispa de Claude. Commit `docs:`.

Ningún paso tiene llamadas pagas ni dependencias nuevas.

## Criterios de aceptación

Cada criterio se verifica pegando el comando y su salida en el PR (constitución, principio 6).

- [ ] `pnpm --dir web test` pasa, incluidos `thinking-orbit.test.ts` y `shimmer-text.test.ts`.
- [ ] `pnpm --dir web check` y `pnpm --dir web rules` pasan.
- [ ] Las pruebas del asesor del 11c pasan sin cambiar sus textos ("Pensando…" visible y pasos en vivo).
- [ ] Con `reducedMotion: "no-preference"`, una bola de `ThinkingOrbit` cambia de posición entre dos lecturas separadas 200 ms. Con `reducedMotion: "reduce"`, no cambia.
- [ ] Al llegar la respuesta, la animación desaparece y no queda ningún `requestAnimationFrame` pendiente (Vitest).
- [ ] Con varios pasos en curso, hay una sola `ThinkingOrbit` y un solo `ShimmerText` en la página, en la misma línea. Los pasos terminados no destellan.
- [ ] Con `reducedMotion: "reduce"`, las letras de `ShimmerText` tienen `animation-name: none`.
- [ ] Un paso largo a 320 px baja de línea entre palabras, nunca a mitad de una (captura).
- [ ] `@axe-core/playwright` no reporta violaciones en `/asesor/` durante la espera, a 390 y 1440 px, incluido el contraste del texto que destella.
- [ ] La CSP no cambia y no hay mensajes `Content Security Policy` en la consola durante la espera.
- [ ] Las capturas del asesor no cambian entre dos corridas seguidas en CI.
- [ ] El PR trae un GIF de unos 3 segundos de la espera, al lado de la vista previa F2 aprobada, y Andrés lo aprueba.
- [ ] El workflow `web.yml` queda en verde en el PR.

## Decisiones tomadas y descartadas

- **Sí:** puntos en órbita con profundidad, variante "giroscopio" a 1,0× (Andrés, 26 nov). **No:** puntos que rebotan, que laten, paso con brillo, casa que respira y barra indeterminada. **No:** F1, la órbita fija, ni F3, tres órbitas cruzadas.
- **Sí:** tomar de Claude solo la idea del movimiento con profundidad. **No:** imitar su chispa, que es la marca de Anthropic y confundiría de quién es el producto.
- **Sí:** `requestAnimationFrame` con `transform` y `opacity`, que no repintan el diseño. **No:** `@keyframes`, que no pueden hacer la perspectiva con la inclinación variable. **No:** una librería de animación, que suma peso por tres puntos.
- **Sí:** una sola animación a la vez, en el último paso en curso. **No:** una por paso, que multiplica los bucles.
- **Sí:** destello del texto por color, solo en la línea en curso (Andrés, 26 nov). **No:** destello por opacidad, que deja el texto sin el contraste mínimo. **No:** destello en los pasos terminados.
- **Sí:** cuadro fijo con movimiento reducido. Así se mantiene lo que buscaba el punto quieto del 11c.

## Riesgos identificados

| Riesgo | Mitigación |
| --- | --- |
| Gasta batería o CPU en móviles | Solo `transform` y `opacity`, un bucle a la vez, que se detiene con la pestaña oculta y al llegar la respuesta |
| A 24 px las bolas se leen como una mancha | La vista previa en Playwright a 390 px es parte de la aprobación. Si no se lee, la caja sube a 28 px antes de integrar |
| Las capturas se vuelven inestables | Movimiento reducido en `visual.spec.ts` y el cuadro fijo determinista |
| Un lector de pantalla deletrea el texto que destella | Letras con `aria-hidden` y el texto completo en `sr-only`. Se verifica con el árbol de accesibilidad en Playwright |
| La CSP bloquea los estilos | Se asignan con el CSSOM desde una referencia, no como atributo en el HTML |

## Lo que **no** entra en este spec

- Animaciones fuera del asesor.
- Cambios en los textos de los pasos o en la región en vivo.
- Ajustes de velocidad o de estilo para el usuario.

Cada uno, si llega, va en su propio spec.
