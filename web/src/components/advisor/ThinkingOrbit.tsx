/** Three balls on a tilting, rolling orbit drawn in perspective while the advisor works (SPEC 11e). */
import { useLayoutEffect, useRef } from "react";

const BALLS = 3;
/** The approved speed (1.0×); a constant, not an option. */
const SPEED = 1;
/** Shown under prefers-reduced-motion: two balls in front at the sides, one behind. */
export const STILL_TIME = 0.12;

export type BallFrame = { transform: string; opacity: string; zIndex: string };

/**
 * Where each ball is at t seconds, for a box of size px: a circle tilted on X (the tilt
 * wobbles), rolled on Z and projected in perspective. Pure, so the frames can be checked by hand.
 */
export function orbitFrame(t: number, size: number): BallFrame[] {
  const r = 0.3 * size;
  const f = 5.4 * r;
  const tilt = ((68 + 16 * Math.sin(1.3 * t)) * Math.PI) / 180;
  const roll = 0.9 * t;
  return Array.from({ length: BALLS }, (_, i) => {
    const a = 4.2 * t + (i * 2 * Math.PI) / BALLS;
    const x = r * Math.cos(a);
    const y = r * Math.sin(a);
    const y2 = y * Math.cos(tilt);
    const z = y * Math.sin(tilt);
    const xr = x * Math.cos(roll) - y2 * Math.sin(roll);
    const yr = x * Math.sin(roll) + y2 * Math.cos(roll);
    const k = f / (f - z);
    const depth = (z / r + 1) / 2; // 0 behind, 1 in front
    return {
      transform: `translate(${px(xr * k)}, ${px(yr * k)}) scale(${round(0.6 + 0.6 * depth)})`,
      opacity: String(round(0.35 + 0.65 * depth)),
      zIndex: String(Math.round(100 * depth)),
    };
  });
}

const round = (n: number) => Math.round(n * 1000) / 1000;
const px = (n: number) => `${round(n)}px`;

/** The parts of the page the loop needs; the browser's in the component, fakes in the tests. */
export type OrbitEnv = {
  requestFrame: (callback: (now: number) => void) => number;
  cancelFrame: (id: number) => void;
  reducedMotion: Pick<MediaQueryList, "matches" | "addEventListener" | "removeEventListener">;
  page: Pick<Document, "hidden" | "addEventListener" | "removeEventListener">;
};

type Styled = { style: Pick<CSSStyleDeclaration, "transform" | "opacity" | "zIndex"> };

/**
 * Draws the orbit on the balls and keeps it moving with requestAnimationFrame, timed by the
 * clock, not by frames. Under reduced motion it draws the still frame and requests none. It
 * stops while the page is hidden and resumes where it was. Returns the function that stops it.
 */
export function animateOrbit(balls: readonly Styled[], size: number, env: OrbitEnv): () => void {
  let elapsed = STILL_TIME; // starts on the still frame, so turning motion on does not jump
  let last: number | null = null;
  let frame: number | null = null;

  const draw = (t: number) => {
    orbitFrame(t, size).forEach((ball, i) => {
      const target = balls[i];
      if (!target) return;
      target.style.transform = ball.transform;
      target.style.opacity = ball.opacity;
      target.style.zIndex = ball.zIndex;
    });
  };

  const tick = (now: number) => {
    // The first frame after a start only sets the clock: time spent stopped is not counted.
    if (last !== null) elapsed += ((now - last) / 1000) * SPEED;
    last = now;
    draw(elapsed);
    frame = env.requestFrame(tick);
  };

  const stop = () => {
    if (frame !== null) env.cancelFrame(frame);
    frame = null;
    last = null;
  };

  const update = () => {
    if (env.reducedMotion.matches) {
      stop();
      draw(STILL_TIME);
    } else if (env.page.hidden) {
      stop();
    } else if (frame === null) {
      frame = env.requestFrame(tick);
    }
  };

  draw(env.reducedMotion.matches ? STILL_TIME : elapsed);
  update();
  env.reducedMotion.addEventListener("change", update);
  env.page.addEventListener("visibilitychange", update);
  return () => {
    stop();
    env.reducedMotion.removeEventListener("change", update);
    env.page.removeEventListener("visibilitychange", update);
  };
}

function browserEnv(): OrbitEnv {
  return {
    requestFrame: (callback) => window.requestAnimationFrame(callback),
    cancelFrame: (id) => window.cancelAnimationFrame(id),
    reducedMotion: window.matchMedia("(prefers-reduced-motion: reduce)"),
    page: document,
  };
}

/**
 * The orbit in a box of size px (24 in StepTrace). Decorative: hidden from screen readers,
 * which hear the line's text. Sizes and frames are set through the CSSOM, never a style
 * attribute, which the CSP blocks.
 */
export function ThinkingOrbit({ size = 24 }: { size?: number }) {
  const box = useRef<HTMLSpanElement>(null);
  const balls = useRef<(HTMLSpanElement | null)[]>([]);

  // A layout effect, so the first frame is drawn before the box is painted.
  useLayoutEffect(() => {
    if (!box.current) return;
    box.current.style.width = `${size}px`;
    box.current.style.height = `${size}px`;
    const targets = balls.current.filter((ball): ball is HTMLSpanElement => ball !== null);
    for (const ball of targets) {
      ball.style.width = `${0.25 * size}px`;
      ball.style.height = `${0.25 * size}px`;
    }
    return animateOrbit(targets, size, browserEnv());
  }, [size]);

  return (
    <span
      ref={box}
      role="presentation"
      className="relative isolate block shrink-0"
      data-testid="thinking-orbit"
    >
      {Array.from({ length: BALLS }, (_, i) => (
        <span
          key={i}
          ref={(el) => {
            balls.current[i] = el;
          }}
          aria-hidden="true"
          className="absolute inset-0 m-auto rounded-full bg-action"
        />
      ))}
    </span>
  );
}
