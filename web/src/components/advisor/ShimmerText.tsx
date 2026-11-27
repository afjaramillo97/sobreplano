/** The running line's text, with a wave of color that sweeps its letters (SPEC 11e). */
import { Fragment, useLayoutEffect, useRef } from "react";

/** Each letter starts this long after the one before it. */
export const LETTER_DELAY_MS = 60;

export type ShimmerLetter = { char: string; delayMs: number };

/**
 * The text split into words, each into letters with the delay of its wave. The delays count
 * letters only, so the wave crosses a space without a pause.
 */
export function shimmerWords(text: string): ShimmerLetter[][] {
  let index = 0;
  return text
    .split(" ")
    .filter((word) => word !== "")
    .map((word) =>
      // Array.from splits by code point, so a letter outside the BMP stays whole.
      Array.from(word, (char) => ({ char, delayMs: index++ * LETTER_DELAY_MS })),
    );
}

type Delayed = { style: Pick<CSSStyleDeclaration, "animationDelay"> };

/** Gives each letter its delay through the CSSOM: a style attribute is blocked by the CSP. */
export function applyShimmerDelays(letters: readonly Delayed[]): void {
  letters.forEach((letter, i) => {
    letter.style.animationDelay = `${i * LETTER_DELAY_MS}ms`;
  });
}

/**
 * The text once, for screen readers and the live region (sr-only), and once drawn letter by
 * letter, hidden from them so nobody hears it spelled. Each letter is drawn from data-char by
 * ::before, so the page holds the text only once: find-in-page and getByText see one copy.
 * Words never break inside; the color wave runs only without prefers-reduced-motion.
 */
export function ShimmerText({ text }: { text: string }) {
  const visible = useRef<HTMLSpanElement>(null);
  const words = shimmerWords(text);

  useLayoutEffect(() => {
    if (!visible.current) return;
    applyShimmerDelays([...visible.current.querySelectorAll<HTMLElement>("[data-char]")]);
  }, [text]);

  return (
    <span data-testid="shimmer-text">
      <span className="sr-only">{text}</span>
      <span ref={visible} aria-hidden="true">
        {words.map((letters, w) => (
          // The text does not change while the line is shown, so the index is a stable key.
          <Fragment key={w}>
            {w > 0 && " "}
            <span className="whitespace-nowrap">
              {letters.map((letter, i) => (
                <span
                  key={i}
                  aria-hidden="true"
                  data-char={letter.char}
                  className="before:content-[attr(data-char)] motion-safe:animate-shimmer"
                />
              ))}
            </span>
          </Fragment>
        ))}
      </span>
    </span>
  );
}
