# 028 — Spend by category view
Status: done
Wave: 2   Lane: C
Blocked by: 025
Integrates with: 015
Read first: docs/ARCHITECTURE.md#transfers

## Goal
Spending breakdown for a period with drill-down from parent category to child to transactions.

## Acceptance criteria
- [x] Category breakdown chart plus a sortable table
- [x] MTD and YTD toggle, plus a custom range
- [x] Prior-period comparison per category
- [x] Click a category to see its transactions
- [x] **Uncategorised shown prominently**, with a direct link to create a rule for it
- [x] Tests: component tests for sorting, range switching, drill-down, and the uncategorised affordance

## Files
- `web/src/app/(dashboard)/spending/page.tsx`
- `web/src/components/charts/category-breakdown.tsx`
- `web/src/components/transaction-table.tsx`

## Notes

`lib/format.ts` has `formatDate` and `formatAge` but no short axis-tick form, so ticket
027's chart declares two local `Intl.DateTimeFormat` instances. This is the second chart
— move a short-date formatter into `format.ts` and have both use it rather than
duplicating a third.

Built against MSW mocks typed from `api-types.ts` — it does **not** wait for the
backend tickets above. Point it at the real endpoints once they land; ticket 038 verifies
the join.

Read the `dataviz` skill for the categorical palette.

Making uncategorised visible is deliberate: it's the feedback loop that keeps the rules engine
current. Hiding it makes the chart prettier and the numbers worse.

`transaction-table.tsx` is shared with ticket 030 — build it here as a standalone component
taking its rows as props, not coupled to this page's data fetching.

## Done — 2026-08-18

Needed a contract change first. The drill from a parent category to its children had
no way to happen: `/spend` returns flat buckets, `/transactions?category_id` matches
one category exactly rather than a subtree, and there is no categories endpoint — so
nothing told the frontend that Groceries belongs to Food. The alternative was
aggregating transactions in the browser, which would re-implement the transfer,
refund, and income rules and disagree with the server the first time one changed.
`parent_id` was added to `SpendBucket` in its own re-freeze commit.

Built against the real endpoints rather than mocks, since Lane A had already landed
015. The MSW fixtures still exist and are what the tests run on.

Two things only the browser showed:

- A new route *directory* is missed by the dev server's file watcher through the
  Docker bind mount. `/spending` 404s until `docker compose restart web`. Noted on
  the `dev` target — it will affect 029 through 033 too.
- The breadcrumb originally appended the selected leaf, so the trail read
  "All categories › Food › Groceries" directly above Food's subtotal. A number under
  a label reads as that label's number. The trail now tracks the breakdown; the
  selection states itself by staying pressed and by titling the panel it opened.

`period-selector.tsx` was added beyond the ticket's file list — the period logic is
page-level state that scopes both the chart and the table, it needs unit tests of its
own boundary arithmetic, and 030 will want the same control.
