"use client";

/**
 * A list of transactions.
 *
 * Presentational on purpose — it takes rows and renders them, and knows nothing
 * about periods, filters, or fetching. Ticket 030 builds the transactions screen on
 * this same component with its own data loading and row actions, so anything this
 * file learns about *where* rows come from is something 030 has to unlearn.
 *
 * A real `<table>` rather than a grid of divs: these are tabular records, the header
 * cells are what let a screen reader announce "Amount, −$45.00" instead of a bare
 * number, and column semantics come free.
 *
 * Selection and inline editing are opt-in. Ticket 028 and the account detail page
 * render it read-only and pass none of those props; the transactions screen passes
 * all of them. Keeping them optional is what lets one component serve both without a
 * mode flag that each caller has to understand.
 */

import type { ResponseOf } from "@/lib/api";
import { CategoryPicker, type Category } from "@/components/category-picker";
import { EmptyState } from "@/components/states";
import { formatCurrency, formatDate } from "@/lib/format";

export type TransactionRow = ResponseOf<"/transactions", "get">["items"][number];

/**
 * A name for this row's controls that is unique on the page.
 *
 * The merchant alone is not: a list of groceries has four "Corner Market" rows, and
 * four selects sharing one accessible name leaves a screen reader user unable to tell
 * which control they are on. The posted date is the natural discriminator in a
 * transaction list, and it is already the first column they hear.
 */
export function rowLabel(row: TransactionRow): string {
  const who = row.merchant ?? row.description ?? `transaction ${row.id}`;
  return `${who} on ${formatDate(row.posted_at)}`;
}

/**
 * How a transaction got its category.
 *
 * `manual` is called out because it is the one the rules engine will not overwrite —
 * seeing it explains why a row keeps a category no rule would give it. The other two
 * are unremarkable and stay quiet rather than adding a badge to every row.
 */
function CategorySource({ source }: { source: TransactionRow["category_source"] }) {
  if (source !== "manual") return null;
  return (
    <span className="border-hairline text-ink-muted ml-1.5 rounded border px-1 py-px text-[10px] tracking-wide uppercase">
      manual
    </span>
  );
}

export function TransactionTable({
  rows,
  caption,
  emptyTitle = "No transactions here",
  emptyDetail,
  categories,
  onRecategorise,
  selectedIds,
  onToggleSelect,
  onToggleAll,
  pendingIds,
}: {
  rows: TransactionRow[];
  caption: string;
  emptyTitle?: string;
  emptyDetail?: string;
  /** Pass with `onRecategorise` to make the category cell editable. */
  categories?: Category[];
  onRecategorise?: (id: number, categoryId: number | null) => void;
  /** Pass all three to add a selection column. */
  selectedIds?: ReadonlySet<number>;
  onToggleSelect?: (id: number) => void;
  onToggleAll?: (checked: boolean) => void;
  /** Rows with a write in flight — dimmed and locked against a second edit. */
  pendingIds?: ReadonlySet<number>;
}) {
  const selectable = Boolean(selectedIds && onToggleSelect && onToggleAll);
  const editable = Boolean(categories && onRecategorise);
  const allSelected =
    selectable && rows.length > 0 && rows.every((row) => selectedIds!.has(row.id));

  if (rows.length === 0) return <EmptyState title={emptyTitle} detail={emptyDetail} />;

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr className="border-hairline text-ink-secondary border-b text-left">
            {selectable ? (
              <th scope="col" className="py-2 pr-2">
                <input
                  type="checkbox"
                  aria-label="Select all on this page"
                  checked={allSelected}
                  onChange={(event) => onToggleAll!(event.target.checked)}
                />
              </th>
            ) : null}
            <th scope="col" className="py-2 pr-3 font-medium">
              Date
            </th>
            <th scope="col" className="py-2 pr-3 font-medium">
              Merchant
            </th>
            <th scope="col" className="py-2 pr-3 font-medium">
              Account
            </th>
            <th scope="col" className="py-2 pr-3 font-medium">
              Category
            </th>
            <th scope="col" className="py-2 pl-3 text-right font-medium">
              Amount
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.id}
              className={`border-hairline/60 border-b last:border-0 ${
                pendingIds?.has(row.id) ? "opacity-50" : ""
              }`}
            >
              {selectable ? (
                <td className="py-2 pr-2">
                  <input
                    type="checkbox"
                    aria-label={`Select ${rowLabel(row)}`}
                    checked={selectedIds!.has(row.id)}
                    onChange={() => onToggleSelect!(row.id)}
                  />
                </td>
              ) : null}
              <td className="text-ink-secondary py-2 pr-3 whitespace-nowrap">
                {formatDate(row.posted_at)}
              </td>
              <td className="py-2 pr-3">
                <span className="block">{row.merchant ?? "—"}</span>
                {row.description && row.description !== row.merchant ? (
                  <span className="text-ink-muted block text-xs">{row.description}</span>
                ) : null}
              </td>
              <td className="text-ink-secondary py-2 pr-3 whitespace-nowrap">{row.account_name}</td>
              <td className="py-2 pr-3">
                {editable ? (
                  <span className="flex items-center gap-1 whitespace-nowrap">
                    <CategoryPicker
                      label={`Category for ${rowLabel(row)}`}
                      categories={categories!}
                      value={row.category?.id ?? null}
                      disabled={pendingIds?.has(row.id)}
                      onChange={(next) => onRecategorise!(row.id, next)}
                    />
                    <CategorySource source={row.category_source} />
                  </span>
                ) : row.category ? (
                  <span className="whitespace-nowrap">
                    {row.category.name}
                    <CategorySource source={row.category_source} />
                  </span>
                ) : (
                  <span className="text-ink-muted">Uncategorised</span>
                )}
                {/* Transfers are excluded from every spend figure, so a transfer
                    turning up in a drill-down needs to say why it does not count. */}
                {row.transfer_group_id ? (
                  <span className="border-hairline text-ink-muted ml-1.5 rounded border px-1 py-px text-[10px] tracking-wide uppercase">
                    transfer
                  </span>
                ) : null}
              </td>
              {/* tabular-nums here and nowhere else on the tile side: this is the
                  column case, where digits must line up down the page. */}
              <td className="py-2 pl-3 text-right font-medium whitespace-nowrap tabular-nums">
                {formatCurrency(row.amount_cents)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
