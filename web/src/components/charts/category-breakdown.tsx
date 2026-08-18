"use client";

/**
 * Spend by category, as a ranked bar chart.
 *
 * Horizontal bars because category names are words, not dates: vertical bars would
 * force the labels to rotate or truncate, and a chart you have to tilt your head to
 * read is one nobody reads.
 *
 * **One hue, not eight.** The palette in `globals.css` reserves its categorical slots
 * for "the pairs a reader has to tell apart in a stacked bar or a multi-line chart" —
 * cases where colour is the *only* thing carrying identity. Here every bar sits
 * directly beside its own name, so colour carries nothing, and eight hues would imply
 * eight meanings that don't exist. It would also break the palette's own rule the
 * moment a ninth category appeared, since there is no ninth slot and cycling is
 * forbidden. Reserving colour for the one distinction that *is* meaningful —
 * uncategorised versus categorised — makes it inform rather than decorate.
 *
 * **Bars are scaled to the largest bucket, not to the total.** Scaling to the total
 * would leave everything below the top two or three as an indistinguishable stub in a
 * mostly-empty row. Share-of-total is the thing a reader would lose by that choice,
 * so it is printed as a number on every row instead of being implied by width.
 */

import type { ResponseOf } from "@/lib/api";
import { formatCurrency, formatSignedCurrency } from "@/lib/format";

export type SpendResponse = ResponseOf<"/spend", "get">;
export type Bucket = SpendResponse["buckets"][number];

/** The uncategorised bucket is the one with no category row behind it. */
export function isUncategorised(bucket: Bucket): boolean {
  return bucket.category_id === null || bucket.category_id === undefined;
}

/** Share of the period's total spend, as a percentage with one decimal. */
export function shareOfTotal(spendCents: number, totalCents: number): string {
  if (totalCents <= 0) return "0.0%";
  return `${((spendCents / totalCents) * 100).toFixed(1)}%`;
}

export function CategoryBreakdown({
  buckets,
  totalCents,
  caption,
  onSelect,
  selectedId,
}: {
  buckets: Bucket[];
  totalCents: number;
  caption: string;
  /** Omit to render a static chart — ticket 030 reuses it that way. */
  onSelect?: (bucket: Bucket) => void;
  selectedId?: number | null;
}) {
  // Negative buckets are possible: a month whose only Travel row is a refund. They
  // get no bar rather than a backwards one, and the amount still reads correctly.
  const widest = Math.max(...buckets.map((bucket) => Math.max(0, bucket.spend_cents)), 1);

  return (
    <ul aria-label={caption} className="space-y-1">
      {buckets.map((bucket) => {
        const uncategorised = isUncategorised(bucket);
        const share = shareOfTotal(bucket.spend_cents, totalCents);
        const width = `${Math.max(0, (bucket.spend_cents / widest) * 100)}%`;
        const selected = selectedId !== undefined && selectedId === (bucket.category_id ?? null);

        const body = (
          <>
            <span className="flex items-baseline justify-between gap-3">
              <span className="flex min-w-0 items-center gap-1.5">
                {uncategorised ? <UncategorisedIcon /> : null}
                <span className="truncate text-sm">{bucket.category_name}</span>
              </span>
              <span className="flex shrink-0 items-baseline gap-2 text-sm">
                <span className="font-medium tabular-nums">
                  {formatCurrency(bucket.spend_cents)}
                </span>
                <span className="text-ink-muted w-12 text-right text-xs tabular-nums">{share}</span>
              </span>
            </span>

            <span
              aria-hidden="true"
              className="bg-hairline/60 mt-1 block h-1.5 w-full overflow-hidden rounded-full"
            >
              <span
                className={`block h-full rounded-full ${
                  uncategorised ? "bg-ink-muted" : "bg-series-1"
                }`}
                style={{ width }}
              />
            </span>
          </>
        );

        // The accessible name says everything the row shows, in one utterance —
        // a screen reader user should not have to reconstruct it from four spans.
        const label =
          `${bucket.category_name}: ${formatCurrency(bucket.spend_cents)}, ${share} of spending` +
          (bucket.change_cents === null || bucket.change_cents === undefined
            ? ""
            : `, ${formatSignedCurrency(bucket.change_cents)} versus the prior period`);

        return (
          <li key={bucket.category_id ?? "uncategorised"}>
            {onSelect ? (
              <button
                type="button"
                aria-label={label}
                aria-pressed={selected}
                onClick={() => onSelect(bucket)}
                className={`hover:bg-surface-2 focus-visible:ring-accent block w-full rounded-lg px-2 py-1.5 text-left transition-colors focus-visible:ring-2 focus-visible:outline-none ${
                  selected ? "bg-surface-2" : ""
                }`}
              >
                {body}
              </button>
            ) : (
              <div aria-label={label} className="px-2 py-1.5">
                {body}
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}

/**
 * Marks the uncategorised bar.
 *
 * Paired with the muted fill rather than replacing it: the palette's rule is that a
 * meaning never rests on hue alone, and "this bucket is a gap in your data" is
 * exactly the meaning worth not losing in greyscale.
 */
function UncategorisedIcon() {
  return (
    <svg viewBox="0 0 16 16" aria-hidden="true" className="text-ink-muted h-3 w-3 fill-current">
      <path d="M8 1a7 7 0 100 14A7 7 0 008 1zM6.2 6a1.8 1.8 0 113.4.8c-.3.5-.85.8-1.1 1.2-.15.25-.2.5-.2 1h-1.5c0-.7.1-1.15.4-1.6.3-.45.8-.7.95-1a.55.55 0 00-.5-.8.6.6 0 00-.6.4H6.2zm1 5.2a.95.95 0 111.9 0 .95.95 0 01-1.9 0z" />
    </svg>
  );
}
