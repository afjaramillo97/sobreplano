/**
 * Class name joining with Tailwind conflict resolution, taught the token names.
 *
 * The plain `cn` reads `text-price-lg` as a color, so `cn("text-price-lg", "text-text-price")`
 * would drop the size. Listing the token scales fixes that; tests/unit/utils.test.ts keeps the
 * lists in sync with tokens/sobreplano.tokens.json.
 */
import { createCn } from "cn/config";

/** Typography styles and font sizes (text-*), from the tokens. */
export const TEXT_SIZES = [
  "xs",
  "sm",
  "md",
  "lg",
  "xl",
  "2xl",
  "3xl",
  "4xl",
  "5xl",
  "display",
  "h1",
  "h2",
  "h3",
  "title",
  "body-lg",
  "body",
  "body-sm",
  "caption",
  "label",
  "price-lg",
  "price",
  "price-pill",
];
export const FONT_WEIGHTS = ["regular", "medium", "bold", "extrabold"];
export const SHADOWS = ["sm", "float"];
export const RADII = ["sm", "md", "lg", "full"];

export const cn = createCn({
  extend: {
    theme: {
      text: TEXT_SIZES,
      "font-weight": FONT_WEIGHTS,
      shadow: SHADOWS,
      radius: RADII,
    },
  },
});
