# 010 — Effective-dated ownership stakes
Status: done
Wave: 1   Lane: —
Blocked by: 009
Read first: docs/ARCHITECTURE.md#users-and-ownership, docs/ARCHITECTURE.md#money

## Goal
The single query helper through which all ownership-adjusted math flows, and the single place
in the codebase where money is rounded. This is the load-bearing ticket of the data model.

## Acceptance criteria
- [x] `effective_stake(account_id, as_of, user_id)` returning the stake in force on a date
- [x] `household_stake(account_id, as_of)` summing all stakes in force
- [x] Every account gets an **explicit 100% stake row at creation** — no implicit default, no special case in the helper
- [x] Invariant enforced and tested: for any account, stakes overlapping any given date sum to ≤ 100%
- [x] A transition helper that closes the current row and opens the new one **atomically** when a stake changes
- [x] `adjust(amount, percentage)` applying `ROUND_HALF_UP` to 2dp — the only rounding site in the codebase
- [x] Tests: unit across mid-history stake changes, open-ended ranges, rejected overlaps, and rounding exactly at the half-cent; property tests over generated stake histories asserting the ≤100% invariant never breaks

## Files
- `api/app/services/ownership.py`
- `api/tests/test_ownership.py`

## Notes
Get this right or every aggregate query gets rewritten later. Effective-dating is what stops a
stake change from retroactively rewriting historical net worth. **Do not simplify it to a
single percentage column.**

Rounding lives here and nowhere else, per account rather than on totals, so the number on
screen always equals the sum of the rows above it. See ARCHITECTURE#rounding.
