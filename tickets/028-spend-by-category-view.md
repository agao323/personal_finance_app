# 028 — Spend by category view
Status: todo
Wave: 2   Lane: C
Blocked by: 025
Integrates with: 015
Read first: docs/ARCHITECTURE.md#transfers

## Goal
Spending breakdown for a period with drill-down from parent category to child to transactions.

## Acceptance criteria
- [ ] Category breakdown chart plus a sortable table
- [ ] MTD and YTD toggle, plus a custom range
- [ ] Prior-period comparison per category
- [ ] Click a category to see its transactions
- [ ] **Uncategorised shown prominently**, with a direct link to create a rule for it
- [ ] Tests: component tests for sorting, range switching, drill-down, and the uncategorised affordance

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
