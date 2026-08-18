"use client";

/**
 * The period a spending view covers.
 *
 * Month to date, year to date, or a custom range. Different from the net worth
 * chart's `RangeSelector`, and deliberately not merged with it: that one picks how
 * much *history* to plot and answers with a from-date and a plotting interval; this
 * one picks a closed window to *total up*, and both ends matter. Sharing a component
 * between them would mean one of the two lying about what its buttons mean.
 *
 * `presetPeriod` is pure so the boundary arithmetic is unit-testable without
 * rendering anything — the same split `rangeQuery` uses.
 */

import { useId } from "react";

export type PeriodKey = "MTD" | "YTD" | "CUSTOM";

export interface Period {
  key: PeriodKey;
  /** Inclusive ISO bounds. The API treats both ends as inclusive. */
  from: string;
  to: string;
}

export const PRESETS: readonly { key: Exclude<PeriodKey, "CUSTOM">; label: string }[] = [
  { key: "MTD", label: "This month" },
  { key: "YTD", label: "This year" },
];

/** Month to date is the default: it is the window you can still act on. */
export const DEFAULT_PERIOD: Exclude<PeriodKey, "CUSTOM"> = "MTD";

function iso(date: Date): string {
  return date.toISOString().slice(0, 10);
}

/**
 * The bounds for a preset, ending today.
 *
 * UTC throughout, matching `formatDate` and `rangeQuery`. A local-time boundary
 * would put "this month" a day out for anyone west of Greenwich on the 1st.
 */
export function presetPeriod(key: Exclude<PeriodKey, "CUSTOM">, today: Date = new Date()): Period {
  const to = iso(today);
  const year = today.getUTCFullYear();
  const from =
    key === "MTD"
      ? iso(new Date(Date.UTC(year, today.getUTCMonth(), 1)))
      : iso(new Date(Date.UTC(year, 0, 1)));
  return { key, from, to };
}

/**
 * How to describe the window in prose.
 *
 * The API's comparison window is the equal-length span immediately before `from` —
 * *not* the previous calendar month, because comparing a 31-day January against a
 * 28-day February shows a spending drop that is only a shorter month. The label says
 * "the previous N days" so the reader knows which comparison they are reading.
 */
export function priorPeriodLabel(period: Period): string {
  const days = Math.max(
    1,
    Math.round(
      (Date.parse(`${period.to}T00:00:00Z`) - Date.parse(`${period.from}T00:00:00Z`)) / 86_400_000,
    ) + 1,
  );
  return days === 1 ? "the previous day" : `the previous ${days} days`;
}

export function PeriodSelector({
  period,
  onChange,
}: {
  period: Period;
  onChange: (next: Period) => void;
}) {
  const fromId = useId();
  const toId = useId();
  const custom = period.key === "CUSTOM";

  return (
    <div className="flex flex-wrap items-center gap-2">
      <div
        role="group"
        aria-label="Period"
        className="border-hairline bg-surface-1 inline-flex rounded-lg border p-0.5"
      >
        {PRESETS.map((preset) => (
          <button
            key={preset.key}
            type="button"
            aria-pressed={period.key === preset.key}
            onClick={() => onChange(presetPeriod(preset.key))}
            className={`rounded-md px-2.5 py-1 text-sm transition-colors ${
              period.key === preset.key
                ? "bg-accent-bg text-accent-strong font-medium"
                : "text-ink-secondary hover:text-ink"
            }`}
          >
            {preset.label}
          </button>
        ))}
        <button
          type="button"
          aria-pressed={custom}
          // Seeded from whatever is on screen, so opening the custom fields never
          // changes the numbers underneath them. Switching to a date picker that
          // silently reset the window would make it a different question.
          onClick={() => onChange({ ...period, key: "CUSTOM" })}
          className={`rounded-md px-2.5 py-1 text-sm transition-colors ${
            custom
              ? "bg-accent-bg text-accent-strong font-medium"
              : "text-ink-secondary hover:text-ink"
          }`}
        >
          Custom
        </button>
      </div>

      {custom ? (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <label htmlFor={fromId} className="text-ink-secondary">
            From
          </label>
          <input
            id={fromId}
            type="date"
            value={period.from}
            // `max`/`min` keep the two inputs from crossing. A reversed range is not
            // an error worth a message — it is a state the control should not permit.
            max={period.to}
            onChange={(event) =>
              onChange({ ...period, key: "CUSTOM", from: event.target.value || period.from })
            }
            className="border-hairline bg-surface-1 rounded-md border px-2 py-1"
          />
          <label htmlFor={toId} className="text-ink-secondary">
            to
          </label>
          <input
            id={toId}
            type="date"
            value={period.to}
            min={period.from}
            onChange={(event) =>
              onChange({ ...period, key: "CUSTOM", to: event.target.value || period.to })
            }
            className="border-hairline bg-surface-1 rounded-md border px-2 py-1"
          />
        </div>
      ) : null}
    </div>
  );
}
