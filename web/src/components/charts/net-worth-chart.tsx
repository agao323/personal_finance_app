"use client";

/**
 * Net worth over time — the chart the whole app is judged on.
 *
 * Hand-rolled inline SVG rather than a charting library. Every library ships a
 * palette, a tooltip, and an axis treatment of its own, and the first day's work is
 * always undoing them; the tokens in `globals.css` already are the chart system, so
 * there is nothing left for a library to contribute except a bundle and a set of
 * defaults to fight. The geometry below is a scale, a path string, and a nearest-x
 * lookup.
 *
 * Decisions worth stating, because each has a wrong-looking alternative:
 *
 * - **Zero is always in the y domain.** The total view is an area, and an area's fill
 *   only means anything measured from zero. The split view puts assets and
 *   liabilities on one scale, where a floating baseline would exaggerate whichever is
 *   smaller. A truncated axis is how a finance chart lies.
 * - **One scale, never two.** Assets and liabilities are both dollars; a second
 *   y-axis would invent a correlation between them that isn't in the data.
 * - **The x scale is time, not point index.** Snapshots are sparse and irregular —
 *   an index scale would draw a three-year gap the same width as a one-day gap.
 * - **The SVG is `aria-hidden` and the data lives in a table.** The tooltip enhances,
 *   it never gates: every value is reachable by screen reader and by keyboard
 *   without a pointer ever touching the plot.
 *
 * The range and mode controls sit inside the card. The usual rule is one filter row
 * above everything it scopes — here this card *is* everything they scope, and the
 * dashboard's Mine/Household toggle is the row above.
 */

import { useEffect, useMemo, useState } from "react";
import type { KeyboardEvent as ReactKeyboardEvent, PointerEvent as ReactPointerEvent } from "react";

import {
  DEFAULT_RANGE,
  RANGE_LABELS,
  RangeSelector,
  rangeQuery,
  type RangeKey,
} from "@/components/charts/range-selector";
import { EmptyState, ErrorState, Skeleton } from "@/components/states";
import type { ViewScope } from "@/components/view-toggle";
import type { ResponseOf } from "@/lib/api";
import { apiFetch } from "@/lib/api";
import {
  formatCompactCurrency,
  formatCurrency,
  formatDate,
  formatShortDate,
  type DateGrain,
} from "@/lib/format";

type Series = ResponseOf<"/net-worth/series", "get">;
type Point = Series["points"][number];

/** Total net worth, or the assets/liabilities split behind it. */
export type ChartMode = "total" | "split";

// ── Geometry ────────────────────────────────────────────────────────────────────
// A fixed viewBox scaled to the container, rather than a measured pixel width. It
// needs no ResizeObserver, renders identically on the server, and keeps the whole
// layout in one coordinate space. The viewBox includes the x-axis band, so the axis
// labels can never fall outside a fixed-height container.

const VIEW_W = 720;
const VIEW_H = 260;
const PAD_TOP = 18;
const PAD_BOTTOM = 30;
const PAD_LEFT = 64;
/** The split view reserves room on the right for its two end labels. */
const PAD_RIGHT = { total: 18, split: 96 } as const;

const PLOT_H = VIEW_H - PAD_TOP - PAD_BOTTOM;

const DAY_MS = 86_400_000;

/**
 * A tick step landing on 1/2/5 × 10ⁿ cents, so axis labels read as round money.
 *
 * Returns integer cents: `formatCompactCurrency` rejects a fractional amount, which
 * is exactly the guard that catches a scale computed in dollars by mistake.
 */
export function niceStep(span: number, targetTicks = 4): number {
  const rough = Math.max(span, 1) / targetTicks;
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const normalised = rough / magnitude;
  const multiple = normalised <= 1 ? 1 : normalised <= 2 ? 2 : normalised <= 5 ? 5 : 10;
  return Math.max(1, Math.round(multiple * magnitude));
}

export interface YScale {
  min: number;
  max: number;
  ticks: number[];
}

/** The y domain and its gridline values, in integer cents, always spanning zero. */
export function yScale(values: number[]): YScale {
  const low = Math.min(0, ...values);
  const observed = Math.max(0, ...values);
  // A history of nothing but zeroes still needs an axis to sit on.
  const high = observed > low ? observed : low + 100_000;

  const step = niceStep(high - low);
  const min = Math.floor(low / step) * step;
  const max = Math.ceil(high / step) * step;

  const ticks: number[] = [];
  for (let value = min; value <= max + step / 2; value += step) ticks.push(Math.round(value));
  return { min, max, ticks };
}

/** Up to `limit` evenly spread indices, always including the first and last. */
export function tickIndices(count: number, limit = 5): number[] {
  if (count <= 0) return [];
  if (count <= limit) return Array.from({ length: count }, (_, index) => index);
  const stride = (count - 1) / (limit - 1);
  return Array.from({ length: limit }, (_, index) => Math.round(index * stride));
}

/** Roughly the width of "Aug 2026" at 11px, plus air on both sides. */
const MIN_TICK_GAP = 72;

/**
 * Which points get an x-axis label.
 *
 * Evenly spread *indices* are not evenly spread *positions* — two snapshots three
 * months apart inside a seven-year history land within a few pixels of each other and
 * their labels overprint. Spacing is checked in plot units and the crowded label is
 * dropped; the first and last always survive, because they are the range.
 */
export function axisTicks(xs: number[], minGap = MIN_TICK_GAP, limit = 5): number[] {
  const last = xs.length - 1;
  if (last < 0) return [];

  const chosen: number[] = [];
  for (const index of tickIndices(xs.length, limit)) {
    if (chosen.length === 0 || xs[index] - xs[chosen[chosen.length - 1]] >= minGap) {
      chosen.push(index);
    }
  }

  if (chosen[chosen.length - 1] !== last) {
    while (chosen.length > 0 && xs[last] - xs[chosen[chosen.length - 1]] < minGap) chosen.pop();
    chosen.push(last);
  }
  return chosen;
}

function timeOf(point: Point): number {
  return Date.parse(`${point.as_of}T00:00:00Z`);
}

function trim(value: number): string {
  return String(Math.round(value * 100) / 100);
}

function pathOf(xs: number[], ys: number[]): string {
  return xs.map((x, index) => `${index === 0 ? "M" : "L"}${trim(x)} ${trim(ys[index])}`).join(" ");
}

function areaOf(xs: number[], ys: number[], baseline: number): string {
  const first = xs[0];
  const last = xs[xs.length - 1];
  return `${pathOf(xs, ys)} L${trim(last)} ${trim(baseline)} L${trim(first)} ${trim(baseline)} Z`;
}

// ── Series ──────────────────────────────────────────────────────────────────────

interface Plot {
  key: string;
  label: string;
  /** Token utilities, so light and dark both come from `globals.css`. */
  stroke: string;
  fill: string;
  swatch: string;
  values: number[];
}

function plotsFor(mode: ChartMode, points: Point[]): Plot[] {
  if (mode === "split") {
    return [
      {
        key: "assets",
        label: "Assets",
        stroke: "stroke-series-1",
        fill: "fill-series-1",
        swatch: "bg-series-1",
        values: points.map((point) => point.assets_cents),
      },
      {
        key: "liabilities",
        label: "Liabilities",
        stroke: "stroke-series-2",
        fill: "fill-series-2",
        swatch: "bg-series-2",
        values: points.map((point) => point.liabilities_cents),
      },
    ];
  }
  return [
    {
      key: "net",
      label: "Net worth",
      stroke: "stroke-series-1",
      fill: "fill-series-1",
      swatch: "bg-series-1",
      values: points.map((point) => point.net_worth_cents),
    },
  ];
}

// ── Component ───────────────────────────────────────────────────────────────────

/** What the last settled request was for, and what it produced. */
interface Loaded {
  key: string;
  series: Series | null;
  error: string | null;
}

export function NetWorthChart({ view }: { view: ViewScope }) {
  const [range, setRange] = useState<RangeKey>(DEFAULT_RANGE);
  const [mode, setMode] = useState<ChartMode>("total");
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  // Ranges already fetched, so flipping 3M → 1Y → 3M does not go back to the network
  // for something the client already holds. Written only from a settled response, so
  // it never causes a cascading render — and read during render, where a ref would be
  // rejected outright by `react-hooks`.
  //
  // Deliberately per-mount and never invalidated. It holds history, which changes only
  // when a balance is recorded — and that happens on another page, so coming back here
  // remounts and starts empty. A cache with invalidation would be a second source of
  // truth for the numbers this app exists to get right.
  const [cache, setCache] = useState<Map<string, Series>>(() => new Map());
  const [active, setActive] = useState<number | null>(null);

  // One state cell holding the request it answers, rather than a `loading` flag set
  // at the top of the effect. A flag would be a synchronous setState inside an
  // effect — a cascading render, and the thing React's lint rule is about. Comparing
  // keys derives the same answer from state that is only ever written by a settled
  // response.
  const key = `${view}|${range}`;

  const cached = cache.get(key) ?? null;

  const loading = cached === null && loaded?.key !== key;
  // An error is only worth showing for the request currently on screen; a failure
  // from an abandoned range is stale the moment the reader picks another one.
  const error = cached === null && loaded?.key === key ? loaded.error : null;
  // A failed request drops the previous render rather than keeping it under a new
  // range's heading — a chart labelled with a range it is not showing is worse than
  // an error message.
  const series = cached;

  useEffect(() => {
    const requested = `${view}|${range}`;
    // Already held. Nothing to fetch and nothing to set — the render above reads it.
    if (cache.has(requested)) return;

    let live = true;
    const { from, interval } = rangeQuery(range);

    apiFetch("/net-worth/series", { query: { view, interval, ...(from ? { from } : {}) } })
      .then((next) => {
        if (!live) return;
        setCache((previous) => new Map(previous).set(requested, next));
        setLoaded({ key: requested, series: next, error: null });
        setActive(null);
      })
      .catch((cause: unknown) => {
        if (!live) return;
        setLoaded({
          key: requested,
          series: null,
          error: cause instanceof Error ? cause.message : "Unknown error",
        });
      });

    // Cleanup runs before the next effect, so a slow response for an abandoned
    // range can never overwrite a fresh one.
    return () => {
      live = false;
    };
  }, [view, range, cache]);

  const points = useMemo(
    () => [...(series?.points ?? [])].sort((a, b) => a.as_of.localeCompare(b.as_of)),
    [series],
  );

  const title = view === "household" ? "Household net worth over time" : "Net worth over time";
  const latest = points.at(-1);
  const plots = useMemo(() => plotsFor(mode, points), [mode, points]);

  return (
    <figure className="border-hairline bg-surface-1 rounded-xl border p-4">
      <figcaption className="flex flex-wrap items-start justify-between gap-x-4 gap-y-3">
        <div>
          <h2 className="text-ink-secondary text-sm">{title}</h2>
          {latest ? (
            <>
              <Summary plots={plots} index={points.length - 1} />
              <p className="text-ink-muted mt-1 text-xs">as of {formatDate(latest.as_of)}</p>
            </>
          ) : error ? null : (
            <Skeleton className="mt-2 h-8 w-44" />
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <ModeToggle mode={mode} onChange={setMode} />
          <RangeSelector value={range} onChange={setRange} />
        </div>
      </figcaption>

      {/* A refetch holds the previous render at reduced opacity. A skeleton here
          would blank a chart the reader is mid-thought about, and the layout would
          jump twice for what is usually a fast request. */}
      <div className={`mt-4 ${loading && series ? "opacity-60 transition-opacity" : ""}`}>
        {error ? (
          <ErrorState title="Net worth history unavailable" detail={error} />
        ) : !series ? (
          <Skeleton className="aspect-[72/26] w-full" />
        ) : points.length === 0 ? (
          <EmptyState
            title="No history yet"
            detail={
              range === "ALL"
                ? "Net worth over time is built from balance snapshots. It appears here as soon as the first balances are recorded."
                : `No snapshots in ${RANGE_LABELS[range]}. Try a longer range.`
            }
          />
        ) : (
          <PlotArea
            points={points}
            plots={plots}
            mode={mode}
            active={active}
            onActiveChange={setActive}
            caption={`${title}, ${RANGE_LABELS[range]}`}
          />
        )}
      </div>
    </figure>
  );
}

/**
 * The latest value per series, keyed by a short stroke of its colour.
 *
 * In the split view this is the legend — always present for two series, so identity
 * never rests on colour alone. In the total view there is one series and the heading
 * already names it, so the key is dropped and the number stands on its own.
 */
function Summary({ plots, index }: { plots: Plot[]; index: number }) {
  const alone = plots.length === 1;

  return (
    <ul
      aria-label="Latest values"
      className={alone ? "mt-1" : "mt-1 flex flex-wrap items-baseline gap-x-5 gap-y-1"}
    >
      {plots.map((plot) => (
        <li key={plot.key} className="flex items-baseline gap-2">
          {alone ? null : (
            <>
              <span
                aria-hidden="true"
                className={`inline-block h-0.5 w-3 rounded-full ${plot.swatch}`}
              />
              <span className="text-ink-secondary text-sm">{plot.label}</span>
            </>
          )}
          <span className={`font-medium tracking-tight ${alone ? "text-2xl" : "text-lg"}`}>
            {formatCurrency(plot.values[index])}
          </span>
        </li>
      ))}
    </ul>
  );
}

function ModeToggle({ mode, onChange }: { mode: ChartMode; onChange: (next: ChartMode) => void }) {
  const options: { value: ChartMode; label: string }[] = [
    { value: "total", label: "Total" },
    { value: "split", label: "Assets & liabilities" },
  ];

  return (
    <div
      role="group"
      aria-label="What to plot"
      className="border-hairline bg-surface-1 inline-flex rounded-lg border p-0.5"
    >
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={mode === option.value}
          onClick={() => onChange(option.value)}
          className={`rounded-md px-2.5 py-1 text-sm transition-colors ${
            mode === option.value
              ? "bg-accent-bg text-accent-strong font-medium"
              : "text-ink-secondary hover:text-ink"
          }`}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

function PlotArea({
  points,
  plots,
  mode,
  active,
  onActiveChange,
  caption,
}: {
  points: Point[];
  plots: Plot[];
  mode: ChartMode;
  active: number | null;
  onActiveChange: (next: number | null) => void;
  caption: string;
}) {
  const last = points.length - 1;
  const padRight = PAD_RIGHT[mode];
  const plotW = VIEW_W - PAD_LEFT - padRight;
  const plotRight = PAD_LEFT + plotW;

  const geometry = useMemo(() => {
    const times = points.map(timeOf);
    const first = times[0];
    const final = times[times.length - 1];
    const span = final - first;

    // One snapshot has no span to spread across: centre it rather than pinning it to
    // the left edge, where it reads like a chart that failed to draw the rest.
    const xs = times.map((time) =>
      span === 0 ? PAD_LEFT + plotW / 2 : PAD_LEFT + ((time - first) / span) * plotW,
    );

    const scale = yScale(plots.flatMap((plot) => plot.values));
    const height = scale.max - scale.min;
    const y = (value: number) => PAD_TOP + (1 - (value - scale.min) / height) * PLOT_H;

    return {
      xs,
      scale,
      y,
      baseline: y(0),
      ys: plots.map((plot) => plot.values.map(y)),
      ticks: axisTicks(xs),
      // A lone label has the whole axis to itself, so it may as well say the year.
      // Otherwise the grain follows the span: "Aug 14" over a quarter, "Aug 2026"
      // over anything longer, where the day is noise.
      grain: (points.length === 1
        ? null
        : span <= 120 * DAY_MS
          ? "day"
          : "month") as DateGrain | null,
    };
  }, [points, plots, plotW]);

  const { xs, scale, y, baseline, ys, ticks, grain } = geometry;

  function move(next: number) {
    onActiveChange(Math.max(0, Math.min(last, next)));
  }

  function onKeyDown(event: ReactKeyboardEvent<HTMLDivElement>) {
    const current = active ?? last;
    switch (event.key) {
      case "ArrowRight":
      case "ArrowUp":
        move(current + 1);
        break;
      case "ArrowLeft":
      case "ArrowDown":
        move(current - 1);
        break;
      case "Home":
        move(0);
        break;
      case "End":
        move(last);
        break;
      case "Escape":
        onActiveChange(null);
        break;
      default:
        return;
    }
    event.preventDefault();
  }

  function onPointerMove(event: ReactPointerEvent<HTMLDivElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    if (rect.width === 0) return;
    const at = ((event.clientX - rect.left) / rect.width) * VIEW_W;
    let nearest = 0;
    for (let index = 1; index < xs.length; index += 1) {
      if (Math.abs(xs[index] - at) < Math.abs(xs[nearest] - at)) nearest = index;
    }
    onActiveChange(nearest);
  }

  // End labels for the split view. Two lines that converge would stack their labels
  // on top of each other, so nudge them apart around their midpoint — the leader is
  // the short horizontal gap to the end dot, which stays unambiguous at 14px apart.
  const endLabels = plots.map((_, series) => ys[series][last]);
  if (endLabels.length === 2 && Math.abs(endLabels[0] - endLabels[1]) < 14) {
    const middle = (endLabels[0] + endLabels[1]) / 2;
    const above = endLabels[0] <= endLabels[1];
    endLabels[0] = middle + (above ? -7 : 7);
    endLabels[1] = middle + (above ? 7 : -7);
  }

  const activePoint = active === null ? null : points[active];
  const tooltipLeft = active === null ? 0 : (xs[active] / VIEW_W) * 100;
  const flip = tooltipLeft > 55;

  return (
    <>
      <div
        role="group"
        tabIndex={0}
        aria-label="Net worth chart. Use the arrow keys to read each point."
        onKeyDown={onKeyDown}
        onFocus={() => onActiveChange(active ?? last)}
        onBlur={() => onActiveChange(null)}
        onPointerMove={onPointerMove}
        onPointerLeave={(event) => {
          if (document.activeElement !== event.currentTarget) onActiveChange(null);
        }}
        className="focus-visible:ring-accent relative rounded-lg focus-visible:ring-2 focus-visible:outline-none"
      >
        {/* The data is in the table below; this is its picture. */}
        <svg
          viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
          className="h-auto w-full"
          aria-hidden="true"
          focusable="false"
        >
          {scale.ticks.map((tick) => (
            <g key={tick}>
              <line
                x1={PAD_LEFT}
                x2={plotRight}
                y1={y(tick)}
                y2={y(tick)}
                strokeWidth={1}
                className={tick === 0 ? "stroke-axis" : "stroke-hairline"}
              />
              <text
                x={PAD_LEFT - 10}
                y={y(tick)}
                textAnchor="end"
                dominantBaseline="middle"
                fontSize={11}
                style={{ fontVariantNumeric: "tabular-nums" }}
                className="fill-ink-muted"
              >
                {formatCompactCurrency(tick)}
              </text>
            </g>
          ))}

          {ticks.map((index) => (
            <text
              key={points[index].as_of}
              x={xs[index]}
              y={VIEW_H - 10}
              textAnchor={
                points.length === 1
                  ? "middle"
                  : index === 0
                    ? "start"
                    : index === last
                      ? "end"
                      : "middle"
              }
              fontSize={11}
              className="fill-ink-muted"
            >
              {grain
                ? formatShortDate(points[index].as_of, grain)
                : formatDate(points[index].as_of)}
            </text>
          ))}

          {/* One point has no line to draw. The dot alone is the honest picture. */}
          {points.length > 1 ? (
            <>
              {mode === "total" ? (
                <path d={areaOf(xs, ys[0], baseline)} className={plots[0].fill} fillOpacity={0.1} />
              ) : null}
              {plots.map((plot, series) => (
                <path
                  key={plot.key}
                  d={pathOf(xs, ys[series])}
                  fill="none"
                  strokeWidth={2}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  className={plot.stroke}
                />
              ))}
            </>
          ) : null}

          {plots.map((plot, series) => (
            <circle
              key={plot.key}
              cx={xs[last]}
              cy={ys[series][last]}
              r={points.length > 1 ? 4 : 5}
              strokeWidth={2}
              className={`${plot.fill} stroke-surface-1`}
            />
          ))}

          {/* Direct labels on the ends, so the two series are identified on the plot
              itself and not only in the legend above it. */}
          {mode === "split"
            ? plots.map((plot, series) => (
                <text
                  key={plot.key}
                  x={xs[last] + 10}
                  y={endLabels[series]}
                  dominantBaseline="middle"
                  fontSize={11}
                  className="fill-ink-secondary"
                >
                  {plot.label}
                </text>
              ))
            : null}

          {active !== null ? (
            <g>
              <line
                x1={xs[active]}
                x2={xs[active]}
                y1={PAD_TOP}
                y2={PAD_TOP + PLOT_H}
                strokeWidth={1}
                className="stroke-axis"
              />
              {plots.map((plot, series) => (
                <circle
                  key={plot.key}
                  cx={xs[active]}
                  cy={ys[series][active]}
                  r={4.5}
                  strokeWidth={2}
                  className={`${plot.fill} stroke-surface-1`}
                />
              ))}
            </g>
          ) : null}
        </svg>

        {/* Always mounted, so a screen reader is listening before the first move. */}
        <div
          role="status"
          aria-live="polite"
          aria-label="Chart readout"
          className="pointer-events-none absolute inset-0"
        >
          {activePoint && active !== null ? (
            <div
              className="absolute top-1"
              style={{
                left: `${tooltipLeft}%`,
                transform: flip ? "translateX(calc(-100% - 10px))" : "translateX(10px)",
              }}
            >
              <div className="border-hairline bg-surface-2 rounded-lg border px-3 py-2 whitespace-nowrap shadow-sm">
                <p className="text-ink-muted text-xs">{formatDate(activePoint.as_of)}</p>
                <ul className="mt-1 space-y-0.5">
                  {plots.map((plot) => (
                    <li key={plot.key} className="flex items-baseline gap-2 text-sm">
                      <span
                        aria-hidden="true"
                        className={`inline-block h-0.5 w-3 rounded-full ${plot.swatch}`}
                      />
                      <span className="font-medium">{formatCurrency(plot.values[active])}</span>
                      <span className="text-ink-secondary text-xs">{plot.label}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          ) : null}
        </div>
      </div>

      {points.length === 1 ? (
        <p className="text-ink-muted mt-2 text-xs">
          One snapshot so far — a line appears once there is a second.
        </p>
      ) : null}

      {/* The table view. Every value the tooltip can show is reachable here without
          a pointer, which is what keeps the tooltip an enhancement. */}
      <table className="sr-only">
        <caption>{caption}</caption>
        <thead>
          <tr>
            <th scope="col">Date</th>
            <th scope="col">Net worth</th>
            <th scope="col">Assets</th>
            <th scope="col">Liabilities</th>
          </tr>
        </thead>
        <tbody>
          {points.map((point) => (
            <tr key={point.as_of}>
              <th scope="row">{formatDate(point.as_of)}</th>
              <td>{formatCurrency(point.net_worth_cents)}</td>
              <td>{formatCurrency(point.assets_cents)}</td>
              <td>{formatCurrency(point.liabilities_cents)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
