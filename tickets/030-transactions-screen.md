# 030 — Transactions screen
Status: done
Wave: 2   Lane: C
Blocked by: 028, 029
Integrates with: 023
Read first: docs/ARCHITECTURE.md#data-model

## Goal
The transactions list with filtering, and the inline controls that set a category by hand or
mark a transfer.

## Acceptance criteria
- [x] Paginated table with date range, account, category, and text filters
- [x] **Uncategorised-only filter**, linked to from the spend view
- [x] Inline category change writing `category_source='manual'`
- [x] Mark-as-transfer control writing `transfer_group_id`
- [x] Bulk categorise for the current filter selection
- [x] Optimistic update with rollback and a visible error on failure
- [x] Reuses `transaction-table.tsx` from 028
- [x] Tests: component tests for each filter, inline recategorisation, bulk categorise, and rollback on a failed PATCH

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

## Done — 2026-08-18

Needed a re-freeze first, for two things the contract did not have: `GET /categories`
(the picker, bulk categorise, and 033's rule editor all need the taxonomy, and
deriving it from `/spend` returns only categories with spending in some window — no
income, no transfer, so "this was a transfer" becomes inexpressible) and
`POST /transactions/bulk-transfer` (`TransactionUpdate` carries only `category_id`, so
the mark-as-transfer criterion had no field to write).

**It also turned up the persistence bug.** Clicking the category picker in the browser
showed the optimistic update, the PATCH returned 200 with the new category in its
body, and reading the row back showed nothing had changed. `get_session` never
committed. Fixed separately — it spans 019, 021 and 023, all of which shipped green.

Two things worth keeping in mind for later screens:

- **Rollback is per row, not a snapshot of the list.** Two writes can be in flight at
  once, and restoring a whole-array snapshot would revert the other row's successful
  change along with the failed one. There is a test for exactly that.
- **A row control's accessible name needs the date.** Four "Corner Market" rows gave
  four selects the same accessible name, which leaves a screen reader user unable to
  tell which one they are on. `rowLabel()` in `transaction-table.tsx` is the shared
  form.

`transaction-table.tsx` gained selection and inline editing as **optional** props, so
028's spend drill-down and 029's account detail keep rendering it read-only with no
mode flag to understand.

The spend view's uncategorised callout now links here with `?uncategorised=true`
instead of opening its own in-page panel. Looking is not fixing, and neither fix — a
manual category or a rule — can happen on that screen. Drilling the uncategorised
*bar* still opens the panel in place, which is the same affordance every other bucket
gets.
