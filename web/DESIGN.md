# Sobreplano design rules

The site uses the Estatery UI kit (DhuhaCreative, UI8) as is. It changes only what it must: AA contrast, content the kit would have us invent, and the logo, which the license does not cover. Where the kit decides, the kit wins. The rules of the curated frontend proposal (§3) apply only where the kit says nothing.

The rules marked **(checked)** fail CI through `pnpm rules` (`scripts/check-design-rules.mjs`), `pnpm test` (contrast) or `pnpm tokens` (generated CSS). The others are checked in review, with the Playwright captures beside the kit screen.

## Rules

1. **One font.** Plus Jakarta Sans variable, served by the site (`@fontsource-variable/plus-jakarta-sans`). No Google Fonts calls. Its space is narrow (0.17 em), so the body adds `word-spacing: 0.05em`. **(checked:** no other families, no `font-serif` or `font-mono`, no Inter, Roboto, Poppins, Montserrat or Playfair**)**
2. **Prices.** Color `text-text-price` (the kit purple), styles `text-price-lg` and `text-price` (800, tracking −1 px). Proportional figures on cards; `tabular-nums` in tables and wherever figures line up in a column.
3. **Radii, borders, shadows.** Radii only from the scale: `rounded-sm` 4, `rounded-md` 8, `rounded-lg` 16, `rounded-full`. The segmented control item uses 6 (8 minus the inset, see `components/ui/tabs.tsx`). Borders are 1.5 px, and 2 px on inputs and outline buttons. Shadows only `shadow-sm` and `shadow-float`. **(checked)**
4. **Colors only from the tokens.** Action `#685DE8`, with `#5245ED` for hover and for text on lavender; the dark button is `#100A55`. The price change goes in the kit's purple badge (the POPULAR shape), never in green or red. **(checked:** no Tailwind default palette, no loose hex, `rgb()`, `hsl()` or `oklch()`**)**
5. **Nothing invented.** No cards inside cards and no 01/02/03 numbering. The kit badge shows only the price change, never "Popular". No testimonials, ratings, or figures that do not come from the data.
6. **Honest "desde".** The "desde" price never appears without its unit type, its date, and the notice of what it may not include.
7. **Errors and empty states.** Errors give the cause and a way out, without apologies. Empty states offer an action.
8. **Motion** lasts 120 to 400 ms (`duration-(--duration-fast)`, `--duration-base`, `--duration-slow`), with no bounce, and is off under `prefers-reduced-motion` (`motion-reduce:transition-none`, `motion-safe:`). That is why the skeleton does not pulse. The one loop is the advisor's waiting animation (SPEC 11e, below), which shows that work is going on; under reduced motion it holds still.
9. **Language.** Colombian Spanish, addressing the reader as **tú**, never mixed with "usted".
10. **Gradient text.** The only gradient text is the second part of the home title, with the `headline-gradient` tokens.
11. **Known exception: the input border.** The kit's input border (`#E0DEF7`, `border-border-input`) reaches only 1.32:1 on white, under the 3:1 that WCAG 1.4.11 asks of a component boundary. It is kept, but every input has a visible label, a lavender fill and a `#685DE8` focus ring (4.86:1).

## Tokens

- **Source:** `tokens/sobreplano.tokens.json`, in DTCG format. It is the draft reviewed on 24 Nov, with no value changes.
- **Generated:** `src/styles/tokens.css`, written by `pnpm tokens`. Never edit it by hand: CI regenerates it and fails on any diff.
- **Contrast:** `tokens/contrast-pairs.json` lists the pairs that must pass AA. `tests/unit/contrast.test.ts` asks 4.5:1 of text and 3:1 of large text, non-text and focus.

Tailwind's default palette, radii, shadows, font weights and sizes are reset, so classes such as `bg-indigo-600`, `rounded-xl` or `font-semibold` generate nothing.

| Need | Use |
| --- | --- |
| Semantic color | `bg-bg-subtle`, `text-text-secondary`, `border-border`, `bg-action`, `hover:bg-action-hover`, `bg-change-bg`, ... (every `color.*` token outside `primitive`, with `default` dropped) |
| shadcn colors | `bg-primary`, `text-muted-foreground`, `ring-ring`, ... (they point at the semantic tokens) |
| Text style | `text-display`, `text-h1` to `text-h3`, `text-title`, `text-body-lg`, `text-body`, `text-body-sm`, `text-caption`, `text-label`, `text-price-lg`, `text-price`, `text-price-pill` (size, line height, tracking and weight together) |
| Weight | `font-regular`, `font-medium`, `font-bold`, `font-extrabold` |
| Spacing | Tailwind's numbers, on a 4 px base (`p-6` = 24 px) |
| Border width | `border-(length:--border-width-default)` 1.5 px, `border-(length:--border-width-strong)` 2 px |
| Sizes | `h-(--size-control-md)`, `max-w-(--size-container)`, `h-(--size-nav)`, ... |
| Motion | `duration-(--duration-fast)`, `ease-out`, `ease-in-out` |

Join classes with `cn` from `@/lib/utils`, never from `cn` directly. The plain one does not know the token names: it reads `text-price-lg` as a color and drops it next to `text-text-price`.

## Components

- **shadcn/ui** components live in `src/components/ui/`. They are copied code, reviewed once when added and adjusted to the kit's measurements. `pnpm rules` skips them, because they use semantic classes (`bg-primary`). Added so far:
  - `button`: kit heights 40/48/56, plus `dark`, `outline` and `soft` variants;
  - `tabs`: the segmented control, and the underlined tabs as variant `line`;
  - `table`: the kit's price history table;
  - `skeleton`: no pulse;
  - `chart`: trimmed to the container and the tooltip. shadcn's `ChartStyle` injects a `<style>` element at run time, which the CSP blocks, so series colors go in through the `style` prop instead;
  - `popover`: the kit's dropdowns, always non-modal (a modal Radix popover locks the scroll with an injected `<style>`);
  - `slider`: 4 px lavender track, action range, white 24 px thumbs with a 2 px action border; each thumb has its own name and value text;
  - `checkbox`: drawn in the action color even unchecked, since the lavender input border falls under 3:1;
  - `switch`: the kit's Toggle on a native `role="switch"` button (SPEC 11c);
  - `sheet` and `select`: shadcn's shape on the native `<dialog>` and `<select>`, not Radix Dialog and Select, which inject `<style>` elements the CSP blocks.
- **No dark variants** (`dark:`) for now. The site has no dark mode, and those classes would half-apply on dark systems.
- **Focus** is a solid 2 px `outline-ring`, offset by 2. A ring at 50 % alpha would fall under 3:1. Hide the resting outline with `outline-hidden`, never `outline-none`: in Tailwind v4 `outline-none` sets `--tw-outline-style: none`, which `focus-visible:outline-2` inherits, so the focus never shows.

## Search and map (SPEC 11b)

From the kit's *Search Result (Map v2)*, *Search Result - Filter (Map v2)*, *Search Result (Swipe Up)* and *Search Map v2*.

- **Layout.** From 1024 px the map is a 16-radius card at the left (sticky, 32 below the nav, 48 from the edge) and the list the right column (736 wide from 1280 px, cards two by two). Below 1024 px the list and the map take turns.
- **Quick filters.** 48 high, 1.5 px `border-input`, 8 radius, `text-body-sm` in `text-muted`, with the kit's lavender circle and chevron. With a value: `action-soft` fill, `action` border, bold `action-soft-text`. Each opens a popover that applies at once.
- **Chips.** One per active filter, `rounded-full` `action-soft` with a close icon; the button's name is "Quitar filtro: …".
- **Price pill.** White (`map-pill`), `rounded-full`, `text-price-pill` in `map-pill-text`, 2 px transparent border; `action` border on hover, focus or when its card is pointed; `map-pill-selected` fill with white text when chosen. Text: "$ 289 M +9,8 %", or "Sin precio". Its name starts with that text (WCAG 2.5.3): "Torre, $ 289 M +9,8 %: desde $ 289.000.000, subió 9,8 %".
- **Group.** A 44 px `action-dark` circle with a white border and the count in `text-label`; a click zooms in until the pills part.
- **Floating card.** The large project card over the map, bottom left (above the bar on phones), with a round close button; it takes the focus, and Esc gives it back to the pill.
- **Map controls.** The zoom is the kit's 40 × 80 white box with `shadow-float`; "N proyectos en esta zona del mapa" and "Buscar al mover el mapa" sit in a white box at the top left. The attribution is always expanded, in the site's caption style.
- **"Ver mapa".** The kit's dark button (`action-dark`, `map-outline` icon), floating at the bottom center of the list below 1024 px. The phone's map view ends in a white bar with "N proyectos en esta zona" and a dark "Ver lista".

## Advisor (SPEC 11c)

From the kit's *Message*, *Message - Empty State* and, on phones, *Message* and *Message - Details*.

- **Layout.** From 1024 px: conversations at the left (351 from 1280 px), the thread in the middle on `bg-subtle` in a 16-radius box, the project at the right (323). The page is as wide as the kit's screen (1440), wider than the site's container, so the thread has room. Below 1024 px the thread takes the screen and the other two open as sheets from its top bar.
- **Bubbles.** The person's: `border-input` fill (the kit's `#E0DEF7`), radius 8 with the bottom-right corner square. The advisor's: white, 1.5 px `border-input`, the top-left corner square, beside a 48 px `bg-selected` circle with the message icon (no photo). Under each: the time and, for answers, the summary of the steps ("Buscó proyectos · Comparó proyectos"), their visible source.
- **Steps.** While a reply runs: "Pensando…", then one line per tool, running or done with a check. The line in progress carries the orbit and the shimmer (below); a step running behind the newest one keeps a still action dot.
- **Small card.** `ProjectCard size="sm"`, after the link card inside the kit's bubble: white, radius 8, a 48 px lavender square with the properties icon, then name, "desde" with its change, unit type and day (rule 6), and place. Only for projects in the build's catalog.
- **Right panel.** The project in context: image, name, place, the "desde" unit type's features, rows (desde, change, developer) and the soft "Ver ficha del proyecto". Without one, the small cards of the projects the conversation named.
- **Composer.** The kit's white box: one line that grows to 160 px, the count at the left and "Enviar" (40 high, `send-bold` icon) at the right. Under it, always, the notice "Respondo con los precios que publican las constructoras. No es asesoría financiera ni una oferta. No escribas datos personales." with the link to the terms.
- **Switch.** The kit's Toggle (`components/ui/switch.tsx`, a native `role="switch"`, not Radix, whose hidden input carries a style attribute the CSP blocks). Off, the thumb is in the action color, since the white one on the lavender track would fall under 3:1.
- **Errors.** In a white box with `role="alert"`, with the cause and a way out (rule 7): retry, the search, or a new conversation.

## Advisor waiting animation (SPEC 11e)

While a reply runs, the line in progress ("Pensando…" or the newest running step) shows three balls on an orbit seen in depth, the "giroscopio", and its text shimmers. Only that line moves: one loop at a time, never on a done step. Code in `components/advisor/ThinkingOrbit.tsx` and `ShimmerText.tsx`.

- **Orbit.** A circle tilted on X (68° ± 16°, wobbling at 1.3 rad/s), rolled on Z (0.9 rad/s) and projected with perspective `F = 5.4·R`; the balls go round at 4.2 rad/s, 120° apart. Depth `d` (0 behind, 1 in front) sets the scale (0.6 to 1.2), the opacity (0.35 to 1) and the z-index. Box 24 px in the steps (the approved preview was 44), radius 30 % of the box, balls 25 % in `bg-action`. Speed 1.0×, a constant. The formulas are in SPEC 11e and in `orbitFrame`.
- **Shimmer.** A wave of color crosses the letters: each goes from `text-secondary` to `action` and back, 1.8 s `ease-in-out`, at `action` at 20 % of the cycle and gray again at 40 %; each letter starts 60 ms after the one before. Color, never opacity: both ends keep 4.5:1 on the white card (`action` 4.86:1), and `tokens/contrast-pairs.json` checks them. Letters are grouped by word, so a long step breaks only between words.
- **Still state.** Under `prefers-reduced-motion: reduce` the orbit shows one fixed frame (t = 0.12 s: two balls in front at the sides, one behind, at least 2 px apart) and starts no loop; the letters have no animation and stay `text-secondary`. It follows a change of the preference while shown. The screenshots use this state.
- **How it moves.** `requestAnimationFrame`, timed by the clock, changing only `transform` and `opacity`; it stops when the line goes away and while the tab is hidden, then resumes where it was. Not `@keyframes`: they cannot project a tilt that changes. No animation library for three dots.
- **CSP.** Every per-frame style and each letter's delay is set through the CSSOM from a ref, never as a `style` attribute, which `style-src` (no `'unsafe-inline'`) blocks. The `shimmer` keyframes live in `styles/global.css` and are used only with `motion-safe:`.
- **Screen readers.** The balls and the letters are `aria-hidden`; the line's text is once in an `sr-only` span, so the live region says "Pensando…" and each step whole, never spelled. The letters are drawn from `data-char` by `::before`, so the page holds the text only once.
- **Not Claude's spark.** Only the idea of motion in depth comes from Claude's animation. Its spark is Anthropic's mark and would blur whose product this is, so the site uses three plain balls in its own action color.

## Calculator, "¿Me alcanza?" and comparison (SPEC 11d)

From the kit's *Tenancy Application* (form cards), *Rental Portfolio* (figures) and the table of the detail page.

- **Form.** White cards, 1.5 px `border-input`, 8 radius, 24 padding, with a bold `text-title`. Inputs 48 high with the label always above, "$" or the unit inside, the error under the field in `text-destructive`, shown once the person leaves it. Money gets its thousands dots on leaving. Choices of two (VIS, area) are the kit's option chips on native radios. The credit settings fold in a `<details>`.
- **Result.** "Puedes comprar hasta" over the price in `text-price-lg`, the limit in a sentence, then a two-column list of figures (one column on a phone), the payment as a share of income on an 8 px bar with marks at 30 and 40 % (the text carries the meaning), the construction months and the button to the search. No sticky column.
- **"¿Me alcanza?".** A card under the price card. Because of it, the project page's right column is no longer sticky: both together are taller than a laptop screen.
- **Comparison table.** Header row on `bg-subtle`, 1.5 px `border` between rows, row headers at the left from 1024 px; below, each label spans two columns over its values. Price per m² in `tabular-nums`; the lowest is marked with the words "Menor $/m²", never color alone. The change badge goes without its icon.
- **Selecting.** "Comparar" in a white chip over the card image's top right corner, a sibling of the card link; the floating "Comparar (N)" bar at the bottom (over the list's column from 1024 px).
- **Finance islands** (JavaScript budget, `docs/frontend.md`): `cx` instead of `cn`, so no class overrides another; the select's chevron is drawn in CSS.
- **Checkbox on a server-rendered island:** native, drawn like `ui/checkbox`. Radix adds a hidden input with a `style` attribute, which the CSP blocks.

## Kit assets

- **Icons** come from the private submodule `kit/` (`sobreplano-kit`, 115 SVG with `currentColor`) through `src/lib/icons.ts`. Without the submodule, the build uses our own drawings in `src/assets/icons-fallback/`. Each icon the site uses must be listed in `ICON_NAMES` and have a fallback; a test checks both.
- **Never commit kit files to this repository:** no `.fig`, PNG, icons, illustrations or photos. The UI8 license forbids redistributing them; they may only ship inside the built site.
- **The project image** `src/assets/project-placeholder.svg` is our own drawing in the kit's purples, not a kit asset. It is decorative (`alt=""`). It may be replaced by an illustration in the same style, never by a realistic photo.
