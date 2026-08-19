"use client";

/**
 * A balance history in the space of a line of text.
 *
 * Deliberately not a small version of the net worth chart. A sparkline answers one
 * question — which way has this been going — and axes, gridlines, and tooltips all
 * cost more space than that answer is worth. It carries no y-axis at all, which is
 * exactly why the endpoints are labelled in the caller: a shape with no scale is
 * decoration, a shape with its first and last value is information.
 *
 * The accessible content is the caller's job for the same reason: the SVG is hidden,
 * and the detail page puts every point in a table beneath it.
 */

const VIEW_W = 240;
const VIEW_H = 44;
const PAD = 3;

export interface SparkPoint {
  as_of: string;
  balance_cents: number;
}

/**
 * Point coordinates in the viewBox.
 *
 * Exported for its own test: the flat-series case divides by a zero range, and a
 * NaN in a path string renders as nothing at all — a silently blank chart rather
 * than a loud failure.
 */
export function sparkGeometry(points: SparkPoint[]): { xs: number[]; ys: number[] } {
  const values = points.map((point) => point.balance_cents);
  const low = Math.min(...values);
  const high = Math.max(...values);
  const range = high - low;

  const plotW = VIEW_W - PAD * 2;
  const plotH = VIEW_H - PAD * 2;
  const step = points.length > 1 ? plotW / (points.length - 1) : 0;

  return {
    xs: points.map((_, index) => (points.length > 1 ? PAD + index * step : VIEW_W / 2)),
    // A flat history has no range to scale against. Centring it draws the truth —
    // a straight line through the middle — where dividing by zero draws nothing.
    ys: values.map((value) =>
      range === 0 ? VIEW_H / 2 : PAD + (1 - (value - low) / range) * plotH,
    ),
  };
}

function trim(value: number): string {
  return String(Math.round(value * 100) / 100);
}

export function Sparkline({ points }: { points: SparkPoint[] }) {
  if (points.length === 0) return null;

  const { xs, ys } = sparkGeometry(points);
  const path = xs
    .map((x, index) => `${index === 0 ? "M" : "L"}${trim(x)} ${trim(ys[index])}`)
    .join(" ");

  return (
    <svg
      viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
      className="h-11 w-full max-w-[15rem]"
      aria-hidden="true"
      focusable="false"
      preserveAspectRatio="none"
    >
      {points.length > 1 ? (
        <path
          d={path}
          fill="none"
          strokeWidth={1.5}
          strokeLinecap="round"
          strokeLinejoin="round"
          vectorEffect="non-scaling-stroke"
          className="stroke-series-1"
        />
      ) : null}
      {/* The last point, so a one-snapshot history is still visible as something. */}
      <circle cx={xs[xs.length - 1]} cy={ys[ys.length - 1]} r={2.5} className="fill-series-1" />
    </svg>
  );
}
