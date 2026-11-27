import { describe, expect, it } from "vitest";
import {
  animateOrbit,
  type BallFrame,
  type OrbitEnv,
  orbitFrame,
  STILL_TIME,
} from "../../src/components/advisor/ThinkingOrbit";

/** translate x, y (px) and scale of a frame's transform. */
function parse(ball: BallFrame) {
  const match = /^translate\((-?[\d.]+)px, (-?[\d.]+)px\) scale\(([\d.]+)\)$/.exec(ball.transform);
  if (!match) throw new Error(`unexpected transform ${ball.transform}`);
  return {
    x: Number(match[1]),
    y: Number(match[2]),
    scale: Number(match[3]),
    opacity: Number(ball.opacity),
    zIndex: Number(ball.zIndex),
  };
}

describe("orbitFrame", () => {
  // Worked by hand from the formulas of SPEC 11e, box of 24 px (R = 7.2, F = 38.88).
  it("at t = 0: ball 0 on the right at mid depth, ball 1 in front, ball 2 behind", () => {
    const [b0, b1, b2] = orbitFrame(0, 24).map(parse);
    // a = 0: y = 0, so z = 0, k = 1, d = 0.5.
    expect(b0).toEqual({ x: 7.2, y: 0, scale: 0.9, opacity: 0.675, zIndex: 50 });
    expect(b1?.x).toBeCloseTo(-4.229, 2);
    expect(b1?.y).toBeCloseTo(2.744, 2);
    expect(b1?.scale).toBeCloseTo(1.141, 2);
    expect(b1?.opacity).toBeCloseTo(0.936, 2);
    expect(b1?.zIndex).toBe(90);
    expect(b2?.x).toBeCloseTo(-3.134, 2);
    expect(b2?.y).toBeCloseTo(-2.033, 2);
    expect(b2?.scale).toBeCloseTo(0.659, 2);
    expect(b2?.opacity).toBeCloseTo(0.414, 2);
    expect(b2?.zIndex).toBe(10);
  });

  it("at t = 1 the orbit has turned, tilted and rolled", () => {
    const [b0, b1, b2] = orbitFrame(1, 24).map(parse);
    expect(b0?.x).toBeCloseTo(-1.405, 2);
    expect(b0?.y).toBeCloseTo(-2.768, 2);
    expect(b0?.scale).toBeCloseTo(0.64, 2);
    expect(b0?.zIndex).toBe(7);
    expect(b1?.x).toBeCloseTo(4.477, 2);
    expect(b1?.y).toBeCloseTo(5.657, 2);
    expect(b1?.zIndex).toBe(51);
    expect(b2?.x).toBeCloseTo(-3.371, 2);
    expect(b2?.y).toBeCloseTo(-2.891, 2);
    expect(b2?.scale).toBeCloseTo(1.156, 2);
    expect(b2?.opacity).toBeCloseTo(0.953, 2);
    expect(b2?.zIndex).toBe(93);
  });

  it("the ball in front has the largest scale and opacity", () => {
    for (const t of [0, 0.5, 1, 2.3, 7]) {
      const balls = orbitFrame(t, 24).map(parse);
      const front = balls.reduce((a, b) => (b.zIndex > a.zIndex ? b : a));
      for (const ball of balls) {
        expect(front.scale).toBeGreaterThanOrEqual(ball.scale);
        expect(front.opacity).toBeGreaterThanOrEqual(ball.opacity);
      }
    }
  });

  it("the still frame has two balls in front at the sides, one behind, at least 2 px apart", () => {
    const balls = orbitFrame(STILL_TIME, 24).map(parse);
    const front = balls.filter((b) => b.zIndex > 50).map((b) => b.x);
    expect(front).toHaveLength(2);
    expect(Math.min(...front)).toBeLessThan(-5);
    expect(Math.max(...front)).toBeGreaterThan(5);
    const behind = balls.find((b) => b.zIndex < 50);
    expect(Math.abs(behind?.x ?? Number.NaN)).toBeLessThan(1);
    // Edge to edge, with the 6 px ball scaled.
    for (let i = 0; i < balls.length; i += 1) {
      for (let j = i + 1; j < balls.length; j += 1) {
        const a = balls[i] as (typeof balls)[number];
        const b = balls[j] as (typeof balls)[number];
        const gap = Math.hypot(a.x - b.x, a.y - b.y) - 3 * a.scale - 3 * b.scale;
        expect(gap).toBeGreaterThanOrEqual(2);
      }
    }
  });
});

type Listener = () => void;

/** A page with a fake clock: frames run only when the test calls step(). */
function fakeEnv({ reduced = false, hidden = false } = {}) {
  const frames = new Map<number, (now: number) => void>();
  const listeners = { change: new Set<Listener>(), visibilitychange: new Set<Listener>() };
  let next = 1;
  let requested = 0;
  const reducedMotion = {
    matches: reduced,
    addEventListener: (_type: string, fn: Listener) => listeners.change.add(fn),
    removeEventListener: (_type: string, fn: Listener) => listeners.change.delete(fn),
  };
  const page = {
    hidden,
    addEventListener: (_type: string, fn: Listener) => listeners.visibilitychange.add(fn),
    removeEventListener: (_type: string, fn: Listener) => listeners.visibilitychange.delete(fn),
  };
  const env = {
    requestFrame: (callback: (now: number) => void) => {
      requested += 1;
      frames.set(next, callback);
      return next++;
    },
    cancelFrame: (id: number) => {
      frames.delete(id);
    },
    reducedMotion,
    page,
  } as unknown as OrbitEnv;
  return {
    env,
    pending: () => frames.size,
    requested: () => requested,
    listeners: () => listeners.change.size + listeners.visibilitychange.size,
    /** Runs the pending frames at now (ms). */
    step(now: number) {
      const due = [...frames.entries()];
      frames.clear();
      for (const [, callback] of due) callback(now);
    },
    setReduced(value: boolean) {
      reducedMotion.matches = value;
      for (const fn of listeners.change) fn();
    },
    setHidden(value: boolean) {
      page.hidden = value;
      for (const fn of listeners.visibilitychange) fn();
    },
  };
}

const newBalls = () =>
  Array.from({ length: 3 }, () => ({ style: { transform: "", opacity: "", zIndex: "" } }));

describe("animateOrbit", () => {
  it("draws the still frame at once and, with reduced motion, requests no frame", () => {
    const page = fakeEnv({ reduced: true });
    const balls = newBalls();
    animateOrbit(balls, 24, page.env);
    expect(page.requested()).toBe(0);
    expect(balls.map((b) => b.style.transform)).toEqual(
      orbitFrame(STILL_TIME, 24).map((b) => b.transform),
    );
  });

  it("moves by the clock, not by frames", () => {
    const page = fakeEnv();
    const balls = newBalls();
    animateOrbit(balls, 24, page.env);
    page.step(1000); // sets the clock
    page.step(1500);
    expect(balls[0]?.style.transform).toBe(orbitFrame(STILL_TIME + 0.5, 24)[0]?.transform);
    page.step(1516);
    expect(balls[0]?.style.transform).toBe(orbitFrame(STILL_TIME + 0.516, 24)[0]?.transform);
  });

  it("stopped, it cancels the pending frame and removes its listeners", () => {
    const page = fakeEnv();
    const stop = animateOrbit(newBalls(), 24, page.env);
    page.step(0);
    expect(page.pending()).toBe(1);
    stop();
    expect(page.pending()).toBe(0);
    expect(page.listeners()).toBe(0);
  });

  it("stops while the page is hidden and resumes where it was", () => {
    const page = fakeEnv();
    const balls = newBalls();
    animateOrbit(balls, 24, page.env);
    page.step(0);
    page.step(400);
    page.setHidden(true);
    expect(page.pending()).toBe(0);
    page.setHidden(false);
    expect(page.pending()).toBe(1);
    page.step(60_000); // the first frame back only sets the clock
    expect(balls[0]?.style.transform).toBe(orbitFrame(STILL_TIME + 0.4, 24)[0]?.transform);
  });

  it("hidden from the start, it waits for the page to show", () => {
    const page = fakeEnv({ hidden: true });
    animateOrbit(newBalls(), 24, page.env);
    expect(page.requested()).toBe(0);
    page.setHidden(false);
    expect(page.pending()).toBe(1);
  });

  it("follows a change of the motion preference while mounted", () => {
    const page = fakeEnv();
    const balls = newBalls();
    animateOrbit(balls, 24, page.env);
    page.step(0);
    page.step(700);
    page.setReduced(true);
    expect(page.pending()).toBe(0);
    expect(balls[1]?.style.transform).toBe(orbitFrame(STILL_TIME, 24)[1]?.transform);
    page.setReduced(false);
    expect(page.pending()).toBe(1);
  });
});
