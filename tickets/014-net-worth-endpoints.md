# 014 — Net worth endpoints
Status: done
Wave: 2   Lane: A
Blocked by: 013
Read first: docs/ARCHITECTURE.md#users-and-ownership

## Goal
Current net worth and the historical time series, both ownership-adjusted, both supporting
the Mine / Household view.

## Acceptance criteria
- [x] `GET /net-worth?as_of=&view=mine|household` returning total plus breakdown by kind
- [x] `GET /net-worth/series?from=&to=&interval=month|day` returning the time series
- [x] Series uses each point's in-force snapshots and stakes
- [x] Carry-forward behaviour documented in the endpoint docstring, matching `balances.balance_in_force`
- [x] Sparse history, empty history, and a single-point series all handled explicitly
- [x] Response shapes match 012 exactly — **no `api-types.ts` change**
- [x] Tests: functional for both endpoints covering empty history, a stake change inside the range, a closed account inside the range, and `view=household` vs `view=mine`

## Files
- `api/app/routers/net_worth.py`
- `api/tests/test_api_net_worth.py`

## Notes

**Decide whether the series carries a staleness signal.** `/net-worth` returns
`stale_account_ids`, but `NetWorthSeries` has no equivalent — so a chart segment built
from balances carried forward for 89 days is indistinguishable from a measured one. On a
sparse history that is most of the line. Either add a per-point stale marker (a response
model change, so it stops and re-freezes through 012) or decide explicitly that the
series does not report it and say why here. Raised by ticket 027, which hit it while
drawing the chart.

If a response shape here doesn't match what 012 froze, the fix is a re-freeze commit against
012, not an edit to the generated types file. Lane C is already building against those shapes.
