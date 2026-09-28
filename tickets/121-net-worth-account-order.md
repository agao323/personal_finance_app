# 121 — The single-date net worth lists accounts in id order
Status: done
Wave: 10   Lane: —
Touches: none
Blocked by: none
Read first: docs/ARCHITECTURE.md#users-and-ownership

## Goal
`net_worth` and `net_worth_series` agree on the order of contributions and stale accounts, so
the suite that pins them to each other stops failing at random.

## Acceptance criteria
- [x] `net_worth` loads accounts ordered by id, as the series path already does.
- [x] A test reorders the table physically (an `UPDATE` moves a row to the end) and asserts the
      contributions still come in id order.

## Files
- `api/app/services/net_worth.py`
- `api/tests/test_net_worth.py`

## Notes
Found during 102: `test_net_worth_series.py` failed intermittently — the two paths returned the
same contributions and the same stale ids in different orders. The single-date path selected
accounts with no `ORDER BY`, so Postgres returned them in physical order, which any update to an
account changes. With the eval tests in the suite it failed on every run, so it was fixed here
rather than left as a separate task.
