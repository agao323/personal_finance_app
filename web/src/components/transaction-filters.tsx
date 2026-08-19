"use client";

/**
 * The filter row for the transactions screen.
 *
 * Its own date inputs rather than `PeriodSelector`: that control offers "this month"
 * and "this year" because a spend total has to cover a closed window to mean
 * anything. A transaction list does not — the most common thing to want is *all* of
 * them, and a preset row with no "everything" option would be answering a question
 * nobody asked.
 *
 * `uncategorised` is a tri-state, not a checkbox. "Any", "only uncategorised", and
 * "only categorised" are three genuinely different questions, and the API distinguishes
 * them; a checkbox would collapse the last two and quietly drop a filter the endpoint
 * supports.
 */

import { useId } from "react";

import { CategoryPicker, type Category } from "@/components/category-picker";

export type AccountOption = { id: number; name: string };

export interface Filters {
  from: string;
  to: string;
  accountId: number | null;
  categoryId: number | null;
  /** null is "any"; true is uncategorised only; false is categorised only. */
  uncategorised: boolean | null;
  search: string;
}

export const EMPTY_FILTERS: Filters = {
  from: "",
  to: "",
  accountId: null,
  categoryId: null,
  uncategorised: null,
  search: "",
};

/**
 * The query for a filter set, with the empties dropped.
 *
 * Sending `from=` or `search=` would make the API interpret an empty string, and
 * `category_id` and `uncategorised` together are contradictory — a category *is* a
 * categorisation, so asking for both is a filter that can only return nothing.
 */
export function filterQuery(filters: Filters): Record<string, string | number | boolean> {
  const query: Record<string, string | number | boolean> = {};
  if (filters.from) query.from = filters.from;
  if (filters.to) query.to = filters.to;
  if (filters.accountId !== null) query.account_id = filters.accountId;
  if (filters.categoryId !== null) query.category_id = filters.categoryId;
  else if (filters.uncategorised !== null) query.uncategorised = filters.uncategorised;
  if (filters.search.trim()) query.search = filters.search.trim();
  return query;
}

/** True when anything is narrowing the list — drives the "clear" affordance. */
export function isFiltered(filters: Filters): boolean {
  return Object.keys(filterQuery(filters)).length > 0;
}

export function TransactionFilters({
  filters,
  accounts,
  categories,
  onChange,
}: {
  filters: Filters;
  accounts: AccountOption[];
  categories: Category[];
  onChange: (next: Filters) => void;
}) {
  const fromId = useId();
  const toId = useId();
  const accountId = useId();
  const searchId = useId();

  function update(patch: Partial<Filters>) {
    onChange({ ...filters, ...patch });
  }

  return (
    <div className="border-hairline bg-surface-1 rounded-xl border p-3">
      <div className="flex flex-wrap items-end gap-x-4 gap-y-3 text-sm">
        <Field id={searchId} label="Search">
          <input
            id={searchId}
            type="search"
            value={filters.search}
            placeholder="Merchant or description"
            onChange={(event) => update({ search: event.target.value })}
            className="border-hairline bg-surface-1 w-52 rounded-md border px-2 py-1"
          />
        </Field>

        <Field id={fromId} label="From">
          <input
            id={fromId}
            type="date"
            value={filters.from}
            max={filters.to || undefined}
            onChange={(event) => update({ from: event.target.value })}
            className="border-hairline bg-surface-1 rounded-md border px-2 py-1"
          />
        </Field>

        <Field id={toId} label="To">
          <input
            id={toId}
            type="date"
            value={filters.to}
            min={filters.from || undefined}
            onChange={(event) => update({ to: event.target.value })}
            className="border-hairline bg-surface-1 rounded-md border px-2 py-1"
          />
        </Field>

        <Field id={accountId} label="Account">
          <select
            id={accountId}
            value={filters.accountId === null ? "" : String(filters.accountId)}
            onChange={(event) =>
              update({ accountId: event.target.value === "" ? null : Number(event.target.value) })
            }
            className="border-hairline bg-surface-1 text-ink rounded-md border px-2 py-1"
          >
            <option value="">Any account</option>
            {accounts.map((account) => (
              <option key={account.id} value={account.id}>
                {account.name}
              </option>
            ))}
          </select>
        </Field>

        <div>
          <span className="text-ink-secondary mb-1 block text-xs">Category</span>
          <CategoryPicker
            label="Filter by category"
            includeAny
            categories={categories}
            value={filters.categoryId}
            // Selecting a category makes "uncategorised only" contradictory, so it
            // is cleared rather than left set and silently ignored by the query.
            onChange={(next) =>
              update({
                categoryId: next,
                uncategorised: next === null ? filters.uncategorised : null,
              })
            }
          />
        </div>

        <div>
          <span className="text-ink-secondary mb-1 block text-xs">Categorised</span>
          <div
            role="group"
            aria-label="Categorisation"
            className="border-hairline bg-surface-1 inline-flex rounded-lg border p-0.5"
          >
            {(
              [
                { value: null, label: "Any" },
                { value: true, label: "Uncategorised" },
                { value: false, label: "Categorised" },
              ] as const
            ).map((option) => (
              <button
                key={String(option.value)}
                type="button"
                aria-pressed={filters.uncategorised === option.value}
                onClick={() => update({ uncategorised: option.value, categoryId: null })}
                className={`rounded-md px-2 py-1 text-sm transition-colors ${
                  filters.uncategorised === option.value
                    ? "bg-accent-bg text-accent-strong font-medium"
                    : "text-ink-secondary hover:text-ink"
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>

        {isFiltered(filters) ? (
          <button
            type="button"
            onClick={() => onChange(EMPTY_FILTERS)}
            className="text-ink-secondary hover:text-ink pb-1 underline underline-offset-4"
          >
            Clear filters
          </button>
        ) : null}
      </div>
    </div>
  );
}

function Field({ id, label, children }: { id: string; label: string; children: React.ReactNode }) {
  return (
    <div>
      <label htmlFor={id} className="text-ink-secondary mb-1 block text-xs">
        {label}
      </label>
      {children}
    </div>
  );
}
