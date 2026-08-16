# 029 — Accounts screens
Status: todo
Wave: 2   Lane: C
Blocked by: 025
Integrates with: 019
Read first: docs/ARCHITECTURE.md#users-and-ownership

## Goal
Accounts list grouped by kind, and account detail showing balance history, ownership stake,
and transactions.

## Acceptance criteria
- [ ] List grouped into liquid, illiquid, liabilities with subtotals
- [ ] Ownership-adjusted **and** raw values both visible wherever they differ
- [ ] Detail page with balance history sparkline, stake history, recent transactions
- [ ] Stake displayed with its **effective dates**, not just the current percentage
- [ ] Stale balances flagged with a prompt to update
- [ ] Closed accounts collapsed into a separate section, not mixed into the totals
- [ ] Empty state that routes to the import flow
- [ ] Tests: component tests for grouping and subtotals, the raw-vs-adjusted display on a 50%-owned account, the stale indicator, and the empty state

## Files
- `web/src/app/(dashboard)/accounts/page.tsx`
- `web/src/app/(dashboard)/accounts/[id]/page.tsx`
- `web/src/components/account-row.tsx`

## Notes
Built against MSW mocks typed from `api-types.ts` — it does **not** wait for the
backend tickets above. Point it at the real endpoints once they land; ticket 038 verifies
the join.

Showing stake effective dates rather than a bare percentage is what makes the effective-dating
visible as a feature instead of hidden plumbing — and it's how you catch a stake entered
against the wrong date, which is otherwise invisible until a historical chart looks wrong.
