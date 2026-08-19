"use client";

/**
 * Spending — where the money went, and what to do about the part you can't explain.
 *
 * Three levels, each a click deeper: parent category → child category → the
 * transactions themselves. The breadcrumb is the only way back up, so it is always
 * present rather than appearing once you are lost.
 *
 * The drill is possible because `/spend?group_by=category` reports each bucket's
 * `parent_id`. Filtering children client-side from one response keeps every figure
 * on screen server-computed: totalling transactions in the browser instead would
 * quietly re-implement the transfer, refund, and income rules that make these numbers
 * trustworthy, and the two would disagree the first time one of them changed.
 *
 * No Mine/Household toggle here, deliberately. Spend is the one figure in the app
 * that is never ownership-adjusted — a $60 grocery charge on a joint card is $60 of
 * spending, not $30, because the groceries were bought once. Offering the toggle
 * would imply an answer that does not exist.
 */

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";

import {
  CategoryBreakdown,
  isUncategorised,
  shareOfTotal,
  type Bucket,
  type SpendResponse,
} from "@/components/charts/category-breakdown";
import {
  DEFAULT_PERIOD,
  PeriodSelector,
  presetPeriod,
  priorPeriodLabel,
  type Period,
} from "@/components/period-selector";
import { EmptyState, ErrorState, Skeleton } from "@/components/states";
import { TransactionTable, type TransactionRow } from "@/components/transaction-table";
import { apiFetch } from "@/lib/api";
import { computeDelta, formatCurrency, formatSignedCurrency } from "@/lib/format";

/** What the last settled request was for, and what it produced. */
interface Loaded<T> {
  key: string;
  data: T | null;
  error: string | null;
}

function message(cause: unknown): string {
  return cause instanceof Error ? cause.message : "Unknown error";
}

// ── Sorting ─────────────────────────────────────────────────────────────────────

export type SortColumn = "category" | "spend" | "change";
export type SortDirection = "asc" | "desc";
export interface Sort {
  column: SortColumn;
  direction: SortDirection;
}

/** Largest spend first — the question the page is asked most often. */
export const DEFAULT_SORT: Sort = { column: "spend", direction: "desc" };

/**
 * Buckets in sort order.
 *
 * A missing `change_cents` sorts as zero rather than dropping out or clustering at an
 * end: "no comparison available" is not "the biggest increase", and a bucket
 * vanishing when you sort by a column it happens to lack is the worst option of the
 * three.
 */
export function sortBuckets(buckets: Bucket[], sort: Sort): Bucket[] {
  const sign = sort.direction === "asc" ? 1 : -1;
  return [...buckets].sort((a, b) => {
    if (sort.column === "category") {
      return sign * a.category_name.localeCompare(b.category_name);
    }
    const left = sort.column === "spend" ? a.spend_cents : (a.change_cents ?? 0);
    const right = sort.column === "spend" ? b.spend_cents : (b.change_cents ?? 0);
    // Ties fall back to name, so the order is stable across re-sorts rather than
    // depending on whatever order the API happened to return.
    return left === right ? a.category_name.localeCompare(b.category_name) : sign * (left - right);
  });
}

/** Clicking the active column flips it; a new column starts at its natural end. */
export function nextSort(current: Sort, column: SortColumn): Sort {
  if (current.column === column) {
    return { column, direction: current.direction === "desc" ? "asc" : "desc" };
  }
  return { column, direction: column === "category" ? "asc" : "desc" };
}

// ── Page ────────────────────────────────────────────────────────────────────────

interface Drill {
  id: number;
  name: string;
}

interface Selection {
  /** Null is the uncategorised bucket. */
  id: number | null;
  name: string;
}

export default function SpendingPage() {
  const [period, setPeriod] = useState<Period>(() => presetPeriod(DEFAULT_PERIOD));
  const [drill, setDrill] = useState<Drill | null>(null);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [sort, setSort] = useState<Sort>(DEFAULT_SORT);
  const [spendLoaded, setSpendLoaded] = useState<Loaded<SpendResponse> | null>(null);
  const [rowsLoaded, setRowsLoaded] = useState<Loaded<TransactionRow[]> | null>(null);

  const groupBy = drill ? "category" : "parent_category";
  const spendKey = `${period.from}|${period.to}|${groupBy}`;

  useEffect(() => {
    let live = true;
    apiFetch("/spend", {
      query: { from: period.from, to: period.to, group_by: groupBy },
    })
      .then((data) => {
        if (live) setSpendLoaded({ key: spendKey, data, error: null });
      })
      .catch((cause: unknown) => {
        if (live) setSpendLoaded({ key: spendKey, data: null, error: message(cause) });
      });
    return () => {
      live = false;
    };
  }, [period.from, period.to, groupBy, spendKey]);

  const selectionKey = selection ? `${period.from}|${period.to}|${selection.id ?? "none"}` : null;

  useEffect(() => {
    if (!selection || !selectionKey) return;
    let live = true;
    apiFetch("/transactions", {
      query: {
        from: period.from,
        to: period.to,
        ...(selection.id === null ? { uncategorised: true } : { category_id: selection.id }),
        limit: 200,
      },
    })
      .then((data) => {
        if (live) setRowsLoaded({ key: selectionKey, data: data.items, error: null });
      })
      .catch((cause: unknown) => {
        if (live) setRowsLoaded({ key: selectionKey, data: null, error: message(cause) });
      });
    return () => {
      live = false;
    };
  }, [period.from, period.to, selection, selectionKey]);

  const spendStale = spendLoaded?.key !== spendKey;
  const spendError = spendStale ? null : spendLoaded?.error;
  const spend = spendLoaded?.error ? null : (spendLoaded?.data ?? null);

  // Under `group_by=category` the response is every leaf in the period, so the
  // children of the drilled parent are a filter rather than another request. A
  // top-level category with spend posted directly to it is its own child — it comes
  // back with `category_id` equal to the parent and no `parent_id` of its own.
  const buckets = useMemo(() => {
    const all = spend?.buckets ?? [];
    if (!drill) return all;
    return all.filter((bucket) => bucket.parent_id === drill.id || bucket.category_id === drill.id);
  }, [spend, drill]);

  const sorted = useMemo(() => sortBuckets(buckets, sort), [buckets, sort]);
  const uncategorised = (spend?.buckets ?? []).find(isUncategorised) ?? null;
  const totalCents = spend?.total_cents ?? 0;
  // Everything below the top level is a slice of the period, so the drilled subtotal
  // is what the chart and table are actually adding up.
  const shownCents = drill ? buckets.reduce((sum, b) => sum + b.spend_cents, 0) : totalCents;

  function reset(next: Period) {
    setPeriod(next);
    setDrill(null);
    setSelection(null);
  }

  function onBucketSelect(bucket: Bucket) {
    if (isUncategorised(bucket)) {
      setSelection({ id: null, name: bucket.category_name });
      return;
    }
    if (!drill) {
      setDrill({ id: bucket.category_id as number, name: bucket.category_name });
      setSelection(null);
      return;
    }
    setSelection({ id: bucket.category_id as number, name: bucket.category_name });
  }

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-xl font-medium tracking-tight">Spending</h1>
        <PeriodSelector period={period} onChange={reset} />
      </div>

      {uncategorised && !drill ? (
        <UncategorisedCallout bucket={uncategorised} totalCents={totalCents} />
      ) : null}

      <div className="border-hairline bg-surface-1 mt-4 rounded-xl border p-4">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-2">
          <div>
            <Breadcrumb
              drill={drill}
              onRoot={() => {
                setDrill(null);
                setSelection(null);
              }}
            />
            {spend ? (
              <p className="mt-1 text-2xl font-medium tracking-tight">
                {formatCurrency(shownCents)}
              </p>
            ) : spendError ? null : (
              <Skeleton className="mt-2 h-8 w-40" />
            )}
          </div>
          {spend ? (
            <p className="text-ink-muted text-xs">
              {spend.excluded_transfer_count > 0
                ? `${spend.excluded_transfer_count} transfer${
                    spend.excluded_transfer_count === 1 ? "" : "s"
                  } excluded. `
                : ""}
              Compared with {priorPeriodLabel(period)}.
            </p>
          ) : null}
        </div>

        <div className={`mt-4 ${spendStale && spend ? "opacity-60 transition-opacity" : ""}`}>
          {spendError ? (
            <ErrorState title="Spending unavailable" detail={spendError} />
          ) : !spend ? (
            <Skeleton className="h-64 w-full" />
          ) : sorted.length === 0 ? (
            <EmptyState
              title="No spending in this period"
              detail="Transfers and income are never counted as spending. Try a longer period, or import some transactions."
            />
          ) : (
            <>
              <CategoryBreakdown
                buckets={buckets}
                totalCents={totalCents}
                caption={`Spending by category, ${period.from} to ${period.to}`}
                onSelect={onBucketSelect}
                selectedId={selection?.id ?? undefined}
              />
              <SpendTable
                buckets={sorted}
                totalCents={totalCents}
                sort={sort}
                onSort={(column) => setSort((current) => nextSort(current, column))}
                onSelect={onBucketSelect}
              />
            </>
          )}
        </div>
      </div>

      {selection ? (
        <TransactionsPanel
          selection={selection}
          loaded={rowsLoaded}
          expectedKey={selectionKey}
          onClose={() => setSelection(null)}
        />
      ) : null}
    </div>
  );
}

// ── Pieces ──────────────────────────────────────────────────────────────────────

/**
 * Uncategorised spend, above the chart rather than inside it.
 *
 * Hiding this makes the chart prettier and the numbers worse: every dollar in here is
 * a dollar the breakdown cannot explain. So the callout states the amount, states the
 * share, and links straight at both ways of fixing it — categorise them by hand on
 * the transactions screen, or write a rule so they stay fixed.
 *
 * Both are links out rather than the in-page drill, because neither fix can happen
 * here. Clicking the uncategorised *bar* still opens the panel in place: that is the
 * same drill every other bucket gets, and looking is not fixing.
 */
function UncategorisedCallout({ bucket, totalCents }: { bucket: Bucket; totalCents: number }) {
  return (
    <div className="border-warning/40 bg-surface-1 mt-4 rounded-xl border p-4">
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
        <div>
          <p className="flex items-center gap-1.5 text-sm font-medium">
            <svg
              viewBox="0 0 16 16"
              aria-hidden="true"
              className="text-warning h-4 w-4 fill-current"
            >
              <path d="M8 1a7 7 0 100 14A7 7 0 008 1zm.75 3.5v4h-1.5v-4h1.5zm0 5.5v1.5h-1.5V10h1.5z" />
            </svg>
            {formatCurrency(bucket.spend_cents)} uncategorised
          </p>
          <p className="text-ink-secondary mt-1 text-sm">
            {shareOfTotal(bucket.spend_cents, totalCents)} of this period&rsquo;s spending is not
            attributed to a category, so the breakdown below cannot explain it.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <Link
            href="/transactions?uncategorised=true"
            className="border-hairline hover:bg-surface-2 rounded-lg border px-3 py-1.5 transition-colors"
          >
            Categorise them
          </Link>
          <Link href="/rules" className="text-accent underline underline-offset-4">
            Create a rule
          </Link>
        </div>
      </div>
    </div>
  );
}

/**
 * Where the breakdown below is pointed.
 *
 * It tracks the *breakdown*, not the selected row — a selected category opens the
 * transactions panel, it does not change which buckets the chart and table are
 * showing. Appending the selection here made the trail end in "Groceries" directly
 * above Food’s subtotal, and a number sitting under a label reads as that label’s
 * number. The selected row states itself, by staying pressed and by titling the
 * panel it opened.
 */
function Breadcrumb({ drill, onRoot }: { drill: Drill | null; onRoot: () => void }) {
  const crumbs: { label: string; onClick?: () => void }[] = [
    { label: "All categories", onClick: drill ? onRoot : undefined },
  ];
  if (drill) crumbs.push({ label: drill.name });

  return (
    <nav aria-label="Category drill-down">
      <ol className="text-ink-secondary flex flex-wrap items-center gap-1 text-sm">
        {crumbs.map((crumb, index) => (
          <li key={crumb.label} className="flex items-center gap-1">
            {index > 0 ? (
              <span aria-hidden="true" className="text-ink-muted">
                ›
              </span>
            ) : null}
            {crumb.onClick ? (
              <button
                type="button"
                onClick={crumb.onClick}
                className="hover:text-ink underline underline-offset-4"
              >
                {crumb.label}
              </button>
            ) : (
              <span aria-current={index === crumbs.length - 1 ? "page" : undefined}>
                {crumb.label}
              </span>
            )}
          </li>
        ))}
      </ol>
    </nav>
  );
}

const COLUMNS: { key: SortColumn; label: string; numeric: boolean }[] = [
  { key: "category", label: "Category", numeric: false },
  { key: "spend", label: "Spend", numeric: true },
  { key: "change", label: "Change", numeric: true },
];

function SpendTable({
  buckets,
  totalCents,
  sort,
  onSort,
  onSelect,
}: {
  buckets: Bucket[];
  totalCents: number;
  sort: Sort;
  onSort: (column: SortColumn) => void;
  onSelect: (bucket: Bucket) => void;
}) {
  return (
    <div className="mt-5 overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        <caption className="sr-only">
          Spending by category, sortable. Currently sorted by {sort.column},{" "}
          {sort.direction === "asc" ? "ascending" : "descending"}.
        </caption>
        <thead>
          <tr className="border-hairline text-ink-secondary border-b text-left">
            {COLUMNS.map((column) => (
              <th
                key={column.key}
                scope="col"
                // `aria-sort` on the header is what tells a screen reader the table
                // is sortable and which way it currently is; the arrow is decoration.
                aria-sort={
                  sort.column === column.key
                    ? sort.direction === "asc"
                      ? "ascending"
                      : "descending"
                    : "none"
                }
                className={`py-2 font-medium ${column.numeric ? "text-right" : ""}`}
              >
                <button
                  type="button"
                  onClick={() => onSort(column.key)}
                  className="hover:text-ink inline-flex items-center gap-1"
                >
                  {column.label}
                  <span aria-hidden="true" className="text-ink-muted text-xs">
                    {sort.column === column.key ? (sort.direction === "asc" ? "↑" : "↓") : "↕"}
                  </span>
                </button>
              </th>
            ))}
            <th scope="col" className="py-2 text-right font-medium">
              Share
            </th>
          </tr>
        </thead>
        <tbody>
          {buckets.map((bucket) => {
            const delta =
              bucket.prior_period_cents === null || bucket.prior_period_cents === undefined
                ? null
                : computeDelta(bucket.spend_cents, bucket.prior_period_cents);
            return (
              <tr
                key={bucket.category_id ?? "uncategorised"}
                className="border-hairline/60 border-b last:border-0"
              >
                <th scope="row" className="py-2 pr-3 text-left font-normal">
                  <button
                    type="button"
                    onClick={() => onSelect(bucket)}
                    className="hover:text-ink underline decoration-dotted underline-offset-4"
                  >
                    {bucket.category_name}
                  </button>
                </th>
                <td className="py-2 pl-3 text-right font-medium tabular-nums">
                  {formatCurrency(bucket.spend_cents)}
                </td>
                {/* Spending more is not "up is good", so the arrow is paired with an
                    explicit tone rather than the tile's default. */}
                <td
                  className={`py-2 pl-3 text-right tabular-nums ${
                    delta === null || delta.direction === "flat"
                      ? "text-ink-muted"
                      : delta.direction === "up"
                        ? "text-delta-down"
                        : "text-delta-up"
                  }`}
                >
                  {delta === null ? (
                    "—"
                  ) : (
                    <>
                      <span aria-hidden="true">
                        {delta.direction === "up" ? "↑" : delta.direction === "down" ? "↓" : "→"}
                      </span>{" "}
                      {formatSignedCurrency(bucket.change_cents ?? 0)}
                      {delta.percent ? (
                        <span className="text-ink-muted ml-1 text-xs">({delta.percent})</span>
                      ) : null}
                    </>
                  )}
                </td>
                <td className="text-ink-muted py-2 pl-3 text-right text-xs tabular-nums">
                  {shareOfTotal(bucket.spend_cents, totalCents)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function TransactionsPanel({
  selection,
  loaded,
  expectedKey,
  onClose,
}: {
  selection: Selection;
  loaded: Loaded<TransactionRow[]> | null;
  expectedKey: string | null;
  onClose: () => void;
}) {
  const stale = loaded?.key !== expectedKey;
  const error = stale ? null : loaded?.error;
  const rows = loaded?.error ? null : (loaded?.data ?? null);

  return (
    <section className="border-hairline bg-surface-1 mt-4 rounded-xl border p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-medium">{selection.name} transactions</h2>
        <button
          type="button"
          onClick={onClose}
          className="text-ink-secondary hover:text-ink text-sm underline underline-offset-4"
        >
          Close
        </button>
      </div>

      <div className="mt-3">
        {error ? (
          <ErrorState title="Transactions unavailable" detail={error} />
        ) : !rows || stale ? (
          <Skeleton className="h-32 w-full" />
        ) : (
          <TransactionTable
            rows={rows}
            caption={`${selection.name} transactions`}
            emptyTitle="No transactions in this category"
            emptyDetail="The category has spending in this period but no rows matched — check the period bounds."
          />
        )}
      </div>
    </section>
  );
}
