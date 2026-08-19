"use client";

/**
 * Transactions — the screen where the rules engine gets trained.
 *
 * This is the only place in the UI that writes `category_source='manual'`, which is
 * the value the whole categorisation design exists to protect: re-running every rule
 * over all history must never overwrite a human decision. The loop it closes runs
 * spend view surfaces uncategorised → this screen fixes it → a rule in 033 keeps it
 * fixed.
 *
 * **Writes are optimistic and roll back.** Categorising thirty rows is a rhythm, and
 * a spinner between each one breaks it. The cost is that a failure has to be visible
 * and undone rather than merely logged, so every write snapshots the rows it touches
 * and restores them on rejection, with the reason on screen. A silent revert would be
 * worse than no optimism at all — the reader would believe an edit that never landed.
 */

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";

import type { Category } from "@/components/category-picker";
import { CategoryPicker } from "@/components/category-picker";
import {
  EMPTY_FILTERS,
  TransactionFilters,
  filterQuery,
  isFiltered,
  type AccountOption,
  type Filters,
} from "@/components/transaction-filters";
import { ErrorState, Skeleton } from "@/components/states";
import { TransactionTable, type TransactionRow } from "@/components/transaction-table";
import { apiFetch } from "@/lib/api";

const PAGE_SIZE = 50;

export default function TransactionsPage() {
  // useSearchParams needs a Suspense boundary above it, or the whole route opts out
  // of static rendering. The fallback is the same skeleton the data load shows.
  return (
    <Suspense fallback={<Skeleton className="h-64 w-full" />}>
      <TransactionsScreen />
    </Suspense>
  );
}

export function TransactionsScreen() {
  const search = useSearchParams();
  // The spend screen links here with ?uncategorised=true. Read once, as the initial
  // state: after that the filter row owns it, and re-reading would fight the reader.
  const [filters, setFilters] = useState<Filters>(() => ({
    ...EMPTY_FILTERS,
    uncategorised: search?.get("uncategorised") === "true" ? true : null,
  }));
  const [offset, setOffset] = useState(0);
  const [rows, setRows] = useState<TransactionRow[] | null>(null);
  const [total, setTotal] = useState(0);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [writeError, setWriteError] = useState<string | null>(null);
  const [selected, setSelected] = useState<ReadonlySet<number>>(new Set());
  const [pending, setPending] = useState<ReadonlySet<number>>(new Set());
  const [accounts, setAccounts] = useState<AccountOption[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [bulkCategory, setBulkCategory] = useState<number | null>(null);

  const query = useMemo(() => filterQuery(filters), [filters]);
  const queryKey = useMemo(() => JSON.stringify({ query, offset }), [query, offset]);

  useEffect(() => {
    let live = true;
    apiFetch("/transactions", { query: { ...query, limit: PAGE_SIZE, offset } })
      .then((data) => {
        if (!live) return;
        setRows(data.items);
        setTotal(data.page.total);
        setLoadError(null);
        // A selection that survived a filter change would act on rows nobody can see.
        setSelected(new Set());
      })
      .catch((cause: unknown) => {
        if (!live) return;
        setRows(null);
        setLoadError(cause instanceof Error ? cause.message : "Unknown error");
      });
    return () => {
      live = false;
    };
    // `queryKey` is the serialised form of both — depending on the object identities
    // would refetch on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queryKey]);

  useEffect(() => {
    let live = true;
    apiFetch("/accounts", { query: { include_closed: true } })
      .then((data) => {
        if (!live) return;
        setAccounts(
          data.groups.flatMap((group) =>
            group.accounts.map((account) => ({ id: account.id, name: account.name })),
          ),
        );
      })
      .catch(() => {
        // The filter row degrades to no account options; the list still works.
        if (live) setAccounts([]);
      });

    apiFetch("/categories")
      .then((data) => {
        if (live) setCategories(data);
      })
      .catch(() => {
        if (live) setCategories([]);
      });

    return () => {
      live = false;
    };
  }, []);

  /**
   * Apply a change to the rows now, and undo it if the server refuses.
   *
   * Rollback restores **only the rows this write touched**, not a snapshot of the
   * whole list. Two writes can be in flight at once — a slow one on row A while row
   * B is edited — and restoring a whole-array snapshot would silently revert B's
   * successful change along with A's failed one. Row-level restore is correct
   * whatever else has landed in between.
   */
  const write = useCallback(
    async (
      ids: number[],
      apply: (row: TransactionRow) => TransactionRow,
      send: () => Promise<unknown>,
    ) => {
      const touched = new Set(ids);
      const previous = new Map(
        (rows ?? []).filter((row) => touched.has(row.id)).map((row) => [row.id, row]),
      );

      setWriteError(null);
      setPending((current) => new Set([...current, ...ids]));
      setRows(
        (current) => current?.map((row) => (touched.has(row.id) ? apply(row) : row)) ?? current,
      );

      try {
        await send();
      } catch (cause: unknown) {
        setRows((current) => current?.map((row) => previous.get(row.id) ?? row) ?? current);
        setWriteError(cause instanceof Error ? cause.message : "The change was not saved.");
      } finally {
        setPending((current) => {
          const next = new Set(current);
          for (const id of ids) next.delete(id);
          return next;
        });
      }
    },
    [rows],
  );

  const categorise = useCallback(
    (id: number, categoryId: number | null) => {
      const category = categories.find((candidate) => candidate.id === categoryId) ?? null;
      return write(
        [id],
        (row) => ({
          ...row,
          category: category
            ? {
                id: category.id,
                name: category.name,
                parent_id: category.parent_id,
                kind: category.kind,
              }
            : null,
          // Matching what the API records: a manual write is what rules must not
          // overwrite, and clearing a category clears its provenance with it.
          category_source: categoryId === null ? null : "manual",
        }),
        () =>
          apiFetch("/transactions/{transaction_id}", {
            method: "patch",
            params: { transaction_id: id },
            body: { category_id: categoryId },
          }),
      );
    },
    [categories, write],
  );

  const bulkCategorise = useCallback(() => {
    const ids = [...selected];
    const category = categories.find((candidate) => candidate.id === bulkCategory) ?? null;
    return write(
      ids,
      (row) => ({
        ...row,
        category: category
          ? {
              id: category.id,
              name: category.name,
              parent_id: category.parent_id,
              kind: category.kind,
            }
          : null,
        category_source: bulkCategory === null ? null : "manual",
      }),
      () =>
        apiFetch("/transactions/bulk-categorise", {
          method: "post",
          body: { transaction_ids: ids, category_id: bulkCategory },
        }),
    );
  }, [selected, categories, bulkCategory, write]);

  const markTransfer = useCallback(() => {
    const ids = [...selected];
    return write(
      ids,
      // A placeholder id until the response lands: the badge is the point, and the
      // real group id arrives with the next load.
      (row) => ({ ...row, transfer_group_id: row.transfer_group_id ?? "pending" }),
      () =>
        apiFetch("/transactions/bulk-transfer", {
          method: "post",
          body: { transaction_ids: ids, linked: true },
        }),
    );
  }, [selected, write]);

  const toggleSelect = useCallback((id: number) => {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const toggleAll = useCallback(
    (checked: boolean) => {
      setSelected(checked ? new Set((rows ?? []).map((row) => row.id)) : new Set());
    },
    [rows],
  );

  const showing = rows?.length ?? 0;
  const first = total === 0 ? 0 : offset + 1;
  const last = offset + showing;

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-xl font-medium tracking-tight">Transactions</h1>
        <p className="text-ink-muted text-sm tabular-nums">
          {rows === null ? "" : `${first}–${last} of ${total}`}
        </p>
      </div>

      <div className="mt-4">
        <TransactionFilters
          filters={filters}
          accounts={accounts}
          categories={categories}
          onChange={(next) => {
            setFilters(next);
            setOffset(0);
          }}
        />
      </div>

      {writeError ? (
        <div className="mt-3">
          <ErrorState
            title="That change was not saved"
            detail={`${writeError} The rows have been put back the way they were.`}
          />
        </div>
      ) : null}

      {selected.size > 0 ? (
        <div className="border-accent/40 bg-surface-1 mt-3 flex flex-wrap items-center gap-3 rounded-xl border p-3 text-sm">
          <span className="font-medium">{selected.size} selected</span>
          <CategoryPicker
            label="Category to apply to the selection"
            categories={categories}
            value={bulkCategory}
            onChange={setBulkCategory}
          />
          <button
            type="button"
            onClick={bulkCategorise}
            className="border-hairline hover:bg-surface-2 rounded-lg border px-3 py-1.5 transition-colors"
          >
            Apply to {selected.size}
          </button>
          <button
            type="button"
            onClick={markTransfer}
            disabled={selected.size < 2}
            title={selected.size < 2 ? "A transfer has two sides — select both" : undefined}
            className="border-hairline hover:bg-surface-2 rounded-lg border px-3 py-1.5 transition-colors disabled:opacity-50"
          >
            Mark as transfer pair
          </button>
          <button
            type="button"
            onClick={() => setSelected(new Set())}
            className="text-ink-secondary hover:text-ink underline underline-offset-4"
          >
            Clear selection
          </button>
        </div>
      ) : null}

      <div className="border-hairline bg-surface-1 mt-3 rounded-xl border p-4">
        {loadError ? (
          <ErrorState title="Transactions unavailable" detail={loadError} />
        ) : rows === null ? (
          <Skeleton className="h-64 w-full" />
        ) : (
          <>
            <TransactionTable
              rows={rows}
              caption="Transactions"
              emptyTitle={
                isFiltered(filters) ? "Nothing matches these filters" : "No transactions yet"
              }
              emptyDetail={
                isFiltered(filters)
                  ? "Widen the date range, or clear the filters to see everything."
                  : "Import a CSV from your bank to get started."
              }
              categories={categories}
              onRecategorise={categorise}
              selectedIds={selected}
              onToggleSelect={toggleSelect}
              onToggleAll={toggleAll}
              pendingIds={pending}
              offerRule
            />

            {total > PAGE_SIZE ? (
              <div className="mt-4 flex items-center justify-between gap-3 text-sm">
                <button
                  type="button"
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                  className="border-hairline hover:bg-surface-2 rounded-lg border px-3 py-1.5 transition-colors disabled:opacity-40"
                >
                  Previous
                </button>
                <span className="text-ink-muted tabular-nums">
                  {first}–{last} of {total}
                </span>
                <button
                  type="button"
                  disabled={last >= total}
                  onClick={() => setOffset(offset + PAGE_SIZE)}
                  className="border-hairline hover:bg-surface-2 rounded-lg border px-3 py-1.5 transition-colors disabled:opacity-40"
                >
                  Next
                </button>
              </div>
            ) : null}
          </>
        )}
      </div>
    </div>
  );
}
