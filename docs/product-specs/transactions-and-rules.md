# Transactions and rules

Where categorisation gets fixed by hand, and where the rules that keep it fixed are written.
After the dashboard, the most-used screens in the app.

## What you can do

**Transactions** (`/transactions`)

- Filter by date range, account, category, **uncategorised only**, and text search over
  merchant and description. Paginated (offset, up to 500 a page).
- **Change a category inline.** This records the category as `manual`, which no rule will
  ever overwrite.
- **Mark transactions as a transfer pair**, or unlink them.
- **Bulk-categorise** the selected rows (recorded as `manual` for every row).
- On an uncategorised row, follow **"rule"** to the rules screen with the merchant prefilled.

**Rules** (`/rules`)

- See rules in priority order and **reorder** them with up / down controls.
- **Create, edit and delete** a rule: pattern, match type (`contains`, `equals`,
  `starts_with`, `regex`), target category.
- **Preview** a pattern before saving — which existing transactions it would match, how many,
  and how many of those are already manual and will not change.
- **Run all rules** over the whole history and see how many transactions changed.

## Rules and edge cases

- **A manual category is never overwritten** by a rule — unconditionally. The screen says so.
- **First match by priority wins**; ties break by creation order, so a re-run is
  deterministic. **Re-running is idempotent** and reports zero changes the second time.
- **No match leaves a row uncategorised** — a real state, surfaced by the spend view. Deleting
  a rule does not clear the categories it set.
- **A rule can target a transfer category**, which is how transfers are classified in bulk.
  Marking a pair links the two sides (`transfer_group_id`) but does **not** by itself keep
  them out of spend — the category's `kind` does
  ([transfers-and-categories](../design-docs/transfers-and-categories.md)).
- A rule matches the merchant, falling back to the description when the merchant is empty.
- A malformed regex is refused when written (422), and so is a pattern with nested
  quantifiers. The preview is explicit, not live-as-you-type: half-written regexes are where
  the catastrophic ones come from, and a pattern change clears a stale preview.
- **Optimistic updates roll back per row** with a visible error, so a failure on one row
  never reverts another row's successful change.
- Reorder swaps two priorities rather than renumbering the list.

## Endpoints

| Method | Path | Notes |
|---|---|---|
| GET | `/transactions?from=&to=&account_id=&category_id=&uncategorised=&search=&limit=&offset=` | |
| PATCH | `/transactions/{transaction_id}` | `{category_id}` — records `manual` |
| POST | `/transactions/bulk-categorise` | `{transaction_ids, category_id}` — all `manual` |
| POST | `/transactions/bulk-transfer` | `{transaction_ids, linked}` |
| GET | `/categories` | The taxonomy, including income and transfer kinds |
| GET POST | `/rules` | |
| PATCH DELETE | `/rules/{rule_id}` | |
| POST | `/rules/apply` | Summary of what changed |
| POST | `/rules/preview` | Runs the engine itself, writes nothing |

## Screens and code

`web/src/app/(dashboard)/transactions/page.tsx`, `rules/page.tsx` —
`components/transaction-table.tsx`, `transaction-filters.tsx`, `category-picker.tsx`,
`rules/rule-list.tsx`, `rules/rule-form.tsx`. API: `services/categorize.py`,
`routers/{transactions,rules,categories}.py`.

## Built by

022 (the engine), 023 (the API and the manual override), 030 (the transactions screen, and
the `/categories` and bulk-transfer re-freeze), 033 (the rules screen and preview).
