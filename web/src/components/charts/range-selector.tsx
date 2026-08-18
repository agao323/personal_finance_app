"use client";

/**
 * Time-range presets for the net worth chart.
 *
 * Presets as a row of buttons, not a calendar: nobody fights a date grid for "last
 * 90 days". A custom range is a Later ticket — this app has one household and five
 * answers cover it.
 *
 * `rangeQuery` is a pure function so the from-date arithmetic is unit-testable
 * without rendering anything. It also picks the `interval`, because the two decisions
 * are the same decision: a day-grained year is 365 points nobody can read, and a
 * month-grained quarter is three.
 */

import type { components } from "@/lib/api-types";

export type Interval = components["schemas"]["Interval"];

export type RangeKey = "3M" | "6M" | "1Y" | "YTD" | "ALL";

export const RANGES: readonly { key: RangeKey; label: string }[] = [
  { key: "3M", label: "3M" },
  { key: "6M", label: "6M" },
  { key: "1Y", label: "1Y" },
  { key: "YTD", label: "YTD" },
  { key: "ALL", label: "All" },
];

/** A year reads as "history" without burying the last few months. */
export const DEFAULT_RANGE: RangeKey = "1Y";

export const RANGE_LABELS: Record<RangeKey, string> = {
  "3M": "the last 3 months",
  "6M": "the last 6 months",
  "1Y": "the last year",
  YTD: "the year to date",
  ALL: "all history",
};

function iso(date: Date): string {
  return date.toISOString().slice(0, 10);
}

/**
 * `months` before `today`, with the day-of-month clamped.
 *
 * `Date.UTC(2026, 1, 31)` rolls forward to 3 March. Three months before 31 May is 28
 * February, so without the clamp the range quietly comes up three days short on the
 * few dates where it matters.
 */
function shiftMonths(today: Date, months: number): Date {
  const target = new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth() + months, 1));
  const lastOfMonth = new Date(
    Date.UTC(target.getUTCFullYear(), target.getUTCMonth() + 1, 0),
  ).getUTCDate();
  target.setUTCDate(Math.min(today.getUTCDate(), lastOfMonth));
  return target;
}

/**
 * The `from` date and `interval` for a preset.
 *
 * All arithmetic is UTC, matching `formatDate` — a range boundary that shifts by
 * timezone silently drops or adds a point at the edge.
 *
 * `from: null` means "everything"; the caller omits the parameter rather than
 * sending an empty string, which the API would have to interpret.
 */
export function rangeQuery(
  range: RangeKey,
  today: Date = new Date(),
): { from: string | null; interval: Interval } {
  switch (range) {
    case "3M":
      return { from: iso(shiftMonths(today, -3)), interval: "day" };
    case "6M":
      return { from: iso(shiftMonths(today, -6)), interval: "week" };
    case "1Y":
      return { from: iso(shiftMonths(today, -12)), interval: "week" };
    case "YTD":
      return { from: iso(new Date(Date.UTC(today.getUTCFullYear(), 0, 1))), interval: "week" };
    case "ALL":
      return { from: null, interval: "month" };
  }
}

export function RangeSelector({
  value,
  onChange,
}: {
  value: RangeKey;
  onChange: (next: RangeKey) => void;
}) {
  return (
    <div
      role="group"
      aria-label="Time range"
      className="border-hairline bg-surface-1 inline-flex rounded-lg border p-0.5"
    >
      {RANGES.map((option) => (
        <button
          key={option.key}
          type="button"
          aria-pressed={value === option.key}
          onClick={() => onChange(option.key)}
          className={`rounded-md px-2.5 py-1 text-sm transition-colors ${
            value === option.key
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
