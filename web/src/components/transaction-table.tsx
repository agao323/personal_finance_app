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
 */

import type { ResponseOf } from "@/lib/api";
import { EmptyState } from "@/components/states";
import { formatCurrency, formatDate } from "@/lib/format";

export type TransactionRow = ResponseOf<"/transactions", "get">["items"][number];

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
}: {
  rows: TransactionRow[];
  caption: string;
  emptyTitle?: string;
  emptyDetail?: string;
}) {
  if (rows.length === 0) return <EmptyState title={emptyTitle} detail={emptyDetail} />;

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr className="border-hairline text-ink-secondary border-b text-left">
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
            <tr key={row.id} className="border-hairline/60 border-b last:border-0">
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
                {row.category ? (
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
