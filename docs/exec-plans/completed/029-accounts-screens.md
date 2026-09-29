# 029 — Accounts screens
Status: done
Wave: 2   Lane: C
Blocked by: 025
Integrates with: 019
Read first: docs/ARCHITECTURE.md#users-and-ownership

## Goal
Accounts list grouped by kind, and account detail showing balance history, ownership stake,
and transactions.

## Acceptance criteria
- [x] List grouped into liquid, illiquid, liabilities with subtotals
- [x] Ownership-adjusted **and** raw values both visible wherever they differ
- [x] Detail page with balance history sparkline, stake history, recent transactions
- [x] Stake displayed with its **effective dates**, not just the current percentage
- [x] Stale balances flagged with a prompt to update
- [x] Closed accounts collapsed into a separate section, not mixed into the totals
- [x] Empty state that routes to the import flow
- [x] Tests: component tests for grouping and subtotals, the raw-vs-adjusted display on a 50%-owned account, the stale indicator, and the empty state

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

## Done — 2026-08-18

**No grand total on the list page.** The API's `AccountList.total_cents` sums every
balance regardless of kind, so it adds a mortgage to a brokerage and produces a number
nobody has. Group subtotals come straight from the API — recomputing them in the
browser would be a second implementation of the ownership adjustment, and it would
round differently, since the server rounds once per account and a sum of
already-rounded values is not guaranteed to match. Net worth stays a dashboard figure
with one source.

**`apiFetch` gained path parameters.** The detail page is the first caller of a
templated route, and interpolating the id then casting the result back to
`"/accounts/{account_id}"` would discard exactly the type inference the client exists
for. `apiFetch("/accounts/{account_id}", { params: { account_id: id } })` keeps the
literal at the call site. A missing parameter throws rather than requesting
`/accounts/%7Baccount_id%7D`.

**The stake table converts half-open ranges for display.** `effective_to` is the first
day the stake no longer applies, so the last day shown is the day before. Printing the
raw bound would claim a day the stake did not cover — and would print the same date as
the *start* of the next stake, which is precisely the off-by-one the table exists to
expose.

Balance history is labelled **raw**: `/accounts/{id}/history` takes no view scope, and
a line silently drawn at 50% under a heading that did not say so is the kind of quiet
wrongness this app is built to avoid.

Two files beyond the ticket's list: `charts/sparkline.tsx` (the detail page's history
picture) and the `(dashboard)` move — the old `app/accounts/page.tsx` placeholder was
outside the route group and would have collided with the new path.

**For 031:** the stale-balance prompt currently links to `/import`, which is the only
way to record a newer balance today. Repoint it at the manual balance form.
