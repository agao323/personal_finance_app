"use client";

/**
 * What the import would do, row by row.
 *
 * Counts alone are not a safety net. "312 rows updated" is equally consistent with a
 * correct mapping and with one that read the wrong column into every merchant field —
 * the only thing that distinguishes them is seeing the parsed values. So this shows
 * the rows: the date it read, the amount it read, the merchant it read, and what it
 * would do with them.
 *
 * Errors are per row, not one banner. A file where four dates failed to parse and 308
 * were fine is a fixable mapping problem; the same file reported as "parse error" is
 * an unusable export, and the reader cannot tell those apart from a summary.
 */

import type { ResponseOf } from "@/lib/api";
import { formatCurrency, formatDate } from "@/lib/format";

export type Preview = ResponseOf<"/import/csv/preview", "post">;
export type PreviewRow = Preview["rows"][number];

const ACTION_LABELS: Record<string, string> = {
  create: "New",
  update: "Changed",
  skip: "Unchanged",
};

/** Rows worth showing first: anything broken, then anything that changes. */
export function orderRows(rows: PreviewRow[]): PreviewRow[] {
  const rank = (row: PreviewRow) =>
    row.errors && row.errors.length > 0 ? 0 : row.action === "skip" ? 2 : 1;
  return [...rows].sort((a, b) => rank(a) - rank(b) || a.row_number - b.row_number);
}

export function ImportPreview({ preview, limit = 50 }: { preview: Preview; limit?: number }) {
  const rows = orderRows(preview.rows);
  const shown = rows.slice(0, limit);
  const broken = rows.filter((row) => row.errors && row.errors.length > 0).length;

  return (
    <div>
      <div className="flex flex-wrap gap-3 text-sm">
        <Count label="New" value={preview.will_create} />
        <Count label="Changed" value={preview.will_update} />
        <Count label="Unchanged" value={preview.will_skip} />
        {broken > 0 ? <Count label="With problems" value={broken} tone="warning" /> : null}
      </div>

      {preview.will_create === 0 && preview.will_update === 0 ? (
        <p className="text-ink-secondary mt-3 text-sm">
          Nothing here would change. You have imported this file already — committing it again is
          safe and does nothing.
        </p>
      ) : null}

      {preview.errors && preview.errors.length > 0 ? (
        <ul className="text-ink-secondary mt-3 list-disc space-y-1 pl-5 text-sm">
          {preview.errors.map((error) => (
            <li key={error}>{error}</li>
          ))}
        </ul>
      ) : null}

      <div className="mt-4 overflow-x-auto">
        <table className="w-full border-collapse text-sm">
          <caption className="sr-only">Rows this import would write</caption>
          <thead>
            <tr className="border-hairline text-ink-secondary border-b text-left">
              <th scope="col" className="py-2 pr-3 font-medium">
                Row
              </th>
              <th scope="col" className="py-2 pr-3 font-medium">
                Action
              </th>
              <th scope="col" className="py-2 pr-3 font-medium">
                Date
              </th>
              <th scope="col" className="py-2 pr-3 font-medium">
                Merchant
              </th>
              <th scope="col" className="py-2 pl-3 text-right font-medium">
                Amount
              </th>
            </tr>
          </thead>
          <tbody>
            {shown.map((row) => {
              const errors = row.errors ?? [];
              return (
                <tr key={row.row_number} className="border-hairline/60 border-b last:border-0">
                  <th
                    scope="row"
                    className="text-ink-muted py-2 pr-3 text-left font-normal tabular-nums"
                  >
                    {row.row_number}
                  </th>
                  <td className="py-2 pr-3">
                    {errors.length > 0 ? (
                      <span className="text-warning inline-flex items-center gap-1">
                        <svg
                          viewBox="0 0 16 16"
                          aria-hidden="true"
                          className="h-3 w-3 fill-current"
                        >
                          <path d="M8 1a7 7 0 100 14A7 7 0 008 1zm.75 3.5v4h-1.5v-4h1.5zm0 5.5v1.5h-1.5V10h1.5z" />
                        </svg>
                        Skipped
                      </span>
                    ) : (
                      <span className={row.action === "skip" ? "text-ink-muted" : ""}>
                        {ACTION_LABELS[row.action] ?? row.action}
                      </span>
                    )}
                  </td>
                  <td className="py-2 pr-3 whitespace-nowrap">
                    {row.posted_at ? formatDate(row.posted_at) : <Unparsed />}
                  </td>
                  <td className="py-2 pr-3">
                    <span className="block">{row.merchant ?? <Unparsed />}</span>
                    {row.description && row.description !== row.merchant ? (
                      <span className="text-ink-muted block text-xs">{row.description}</span>
                    ) : null}
                    {errors.length > 0 ? (
                      <span className="text-critical-text block text-xs">{errors.join("; ")}</span>
                    ) : null}
                  </td>
                  <td className="py-2 pl-3 text-right font-medium whitespace-nowrap tabular-nums">
                    {row.amount_cents === null || row.amount_cents === undefined ? (
                      <Unparsed />
                    ) : (
                      formatCurrency(row.amount_cents)
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {rows.length > shown.length ? (
        <p className="text-ink-muted mt-3 text-xs">
          Showing {shown.length} of {rows.length} rows. Problems and changes are listed first.
        </p>
      ) : null}
    </div>
  );
}

/** A blank cell reads as a rendering bug; this reads as a parsing result. */
function Unparsed() {
  return <span className="text-ink-muted italic">could not read</span>;
}

function Count({ label, value, tone }: { label: string; value: number; tone?: "warning" }) {
  return (
    <span
      className={`border-hairline rounded-lg border px-3 py-1.5 ${
        tone === "warning" ? "border-warning/40" : ""
      }`}
    >
      <span className="font-medium tabular-nums">{value}</span>{" "}
      <span className="text-ink-secondary">{label}</span>
    </span>
  );
}
