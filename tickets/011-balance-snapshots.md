# 011 — Balance snapshots
Status: done
Wave: 1   Lane: —
Blocked by: 009
Read first: docs/ARCHITECTURE.md#data-model

## Goal
The write path that guarantees every balance change appends a snapshot, and the lookup that
resolves an account's balance on any past date. History that isn't captured cannot be
recovered later.

## Acceptance criteria
- [x] `record_balance(account_id, as_of, balance, source)` upserting a snapshot for a date
- [x] `balance_in_force(account_id, as_of)` returning the latest snapshot at or before `as_of`
- [x] Carry-forward capped at **3 months**; beyond that the value is returned flagged stale, not dropped
- [x] Accounts with `closed_at <= as_of` return nothing
- [x] Current balance is **derived** as the latest snapshot — never stored on `accounts`
- [x] Tests: unit for same-day overwrite, out-of-order inserts, gaps, the staleness boundary on both sides, and a closed account

## Files
- `api/app/services/balances.py`
- `api/tests/test_balances.py`

## Notes
Deriving current balance from the snapshot table rather than duplicating it on `accounts`
removes a whole class of consistency bug. Accept the extra join.

The staleness cap and `closed_at` together are what stop a sold car from sitting in your net
worth forever — carry-forward is required for a usable chart, and unbounded carry-forward is a
correctness bug.
