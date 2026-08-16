# 030 — Transactions screen
Status: todo
Wave: 2   Lane: C
Blocked by: 028, 029
Integrates with: 023
Read first: docs/ARCHITECTURE.md#data-model

## Goal
The transactions list with filtering, and the inline controls that set a category by hand or
mark a transfer.

## Acceptance criteria
- [ ] Paginated table with date range, account, category, and text filters
- [ ] **Uncategorised-only filter**, linked to from the spend view
- [ ] Inline category change writing `category_source='manual'`
- [ ] Mark-as-transfer control writing `transfer_group_id`
- [ ] Bulk categorise for the current filter selection
- [ ] Optimistic update with rollback and a visible error on failure
- [ ] Reuses `transaction-table.tsx` from 028
- [ ] Tests: component tests for each filter, inline recategorisation, bulk categorise, and rollback on a failed PATCH

## Files
- `web/src/app/(dashboard)/transactions/page.tsx`
- `web/src/components/transaction-filters.tsx`
- `web/src/components/category-picker.tsx`

## Notes
Built against MSW mocks typed from `api-types.ts` — it does **not** wait for the
backend tickets above. Point it at the real endpoints once they land; ticket 038 verifies
the join.

This screen is where the rules engine gets trained, and after the dashboard it's the most-used
screen in the app. It's also the only place `category_source='manual'` is ever written from the
UI — the value the whole categorisation design protects.

The loop this closes: spend view surfaces uncategorised → this screen fixes it → a rule gets
written in 033 so it stays fixed.
