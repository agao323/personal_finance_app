# 014 — Net worth endpoints
Status: todo
Wave: 2   Lane: A
Blocked by: 013
Read first: docs/ARCHITECTURE.md#users-and-ownership

## Goal
Current net worth and the historical time series, both ownership-adjusted, both supporting
the Mine / Household view.

## Acceptance criteria
- [ ] `GET /net-worth?as_of=&view=mine|household` returning total plus breakdown by kind
- [ ] `GET /net-worth/series?from=&to=&interval=month|day` returning the time series
- [ ] Series uses each point's in-force snapshots and stakes
- [ ] Carry-forward behaviour documented in the endpoint docstring, matching `balances.balance_in_force`
- [ ] Sparse history, empty history, and a single-point series all handled explicitly
- [ ] Response shapes match 012 exactly — **no `api-types.ts` change**
- [ ] Tests: functional for both endpoints covering empty history, a stake change inside the range, a closed account inside the range, and `view=household` vs `view=mine`

## Files
- `api/app/routers/net_worth.py`
- `api/tests/test_api_net_worth.py`

## Notes
If a response shape here doesn't match what 012 froze, the fix is a re-freeze commit against
012, not an edit to the generated types file. Lane C is already building against those shapes.
