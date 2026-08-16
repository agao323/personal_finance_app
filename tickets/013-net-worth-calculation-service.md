# 013 — Net worth calculation service
Status: todo
Wave: 2   Lane: A
Blocked by: 012
Read first: docs/ARCHITECTURE.md#users-and-ownership

## Goal
The single ownership-adjusted net worth calculation that every endpoint and chart calls. No
other code path sums balances.

## Acceptance criteria
- [ ] `net_worth(as_of, viewer_id)` returning the ownership-adjusted total plus a breakdown by `kind`
- [ ] `viewer_id=None` returns the household total across all stakes
- [ ] Uses the snapshot in force on `as_of` per account — not just the latest
- [ ] Uses the ownership stake in force on `as_of` — not today's
- [ ] Liabilities subtract
- [ ] Accounts with no snapshot before `as_of` are **excluded, not treated as zero**
- [ ] Accounts closed on or before `as_of` are excluded
- [ ] Stale-flagged balances are included but the response reports how many
- [ ] Rounds via `services/ownership.adjust()` per account, then sums — the total equals the sum of the rows
- [ ] Tests: unit with hand-computed expected values for a date before and after a stake change, a closed account, a stale snapshot, an account with no prior snapshot, and viewer vs household

## Files
- `api/app/services/net_worth.py`
- `api/tests/test_net_worth.py`

## Notes
"In force on `as_of`" is subtle and load-bearing for the history chart: asking for net worth on
a past date must use that date's balances and that date's ownership stakes, not today's. If
this is wrong, every point on the chart except the last one is wrong, and it looks plausible.
