# 052 — The net worth series issues thousands of queries
Status: todo
Wave: 6   Lane: —
Blocked by: none
Read first: docs/ARCHITECTURE.md#ownership-is-applied-in-exactly-one-place

## Goal
Switching the chart between 3M / 6M / 1Y feels instant.

## What was measured

`net_worth_series` is `[net_worth(session, day, viewer) for day in _walk(...)]`, and each
`net_worth` call runs one query for the account list plus **two per account** — one for
`balance_in_force`, one for the stake. Against the seeded database (9 accounts), on local
Postgres over loopback:

| Range | Interval | Points | Queries | Local time |
|---|---|---|---|---|
| 3M | day | 91 | **1,548** | 0.46s |
| 6M | day | 183 | 3,112 | 0.76s |
| 1Y | day | 366 | 6,479 | 1.58s |
| 1Y | week | 54 | 957 | 0.24s |
| 1Y | month | 13 | 232 | 0.06s |

The frontend asks for `day` on 3M and `week` on 6M / 1Y / YTD, so **3M is the worst case
in practice at ~1,548 queries**. Local timings understate it badly: every one of those is
a network round trip to Neon in production, where even a pooled query is milliseconds
rather than microseconds.

## Acceptance criteria
- [ ] The series loads accounts, snapshots and stakes **once** and walks the dates in
      memory. Query count is bounded and independent of the number of points
- [ ] **`net_worth()` is not touched.** It is one date, its cost is fine, and it is what
      `/net-worth`, the export, and every other caller use. Rewriting it to share the new
      path would put the most important number in the app at risk for a chart's benefit
- [ ] **A test asserts the two agree**, point for point, over a fixture with a part-owned
      account, a mid-history stake change, a closed account, and a stale balance. This is
      the criterion that matters: the risk here is a *second* implementation of the
      ownership and carry-forward semantics that drifts from the first, and the only real
      protection is a test that fails when it does
- [ ] A test asserts the query count stays bounded — a fixed small number for a long
      range, so a future change that reintroduces a per-point query fails loudly rather
      than getting slower quietly
- [ ] Rounding still happens exactly once per account in `services/ownership.py`. The
      new path calls `adjust()` the same way; it must not sum raw balances
- [ ] Carry-forward, the 90-day staleness cap, closed-account exclusion, and
      "no stake that day means excluded, not zero" all behave identically
- [ ] The chart caches by `view|range`, so switching back to a range already loaded does
      not refetch

## Files
- `api/app/services/net_worth.py`
- `api/tests/test_net_worth.py`
- `web/src/components/charts/net-worth-chart.tsx`

## Notes

**Half-open stake ranges.** `[effective_from, effective_to)` — the day a stake changes
belongs to the new row. The in-memory lookup has to match `ownership._in_force_on`
exactly, including `effective_to IS NULL` meaning open-ended.

**Snapshots must be sorted ascending per account and searched for the latest at or
before the date.** Not "the first at or after", and not the global latest.

**No caching layer, no materialised view, no denormalised running total.** The data is
one household's; the problem is the number of round trips, not the amount of work. A
cache would add invalidation to a system whose whole design is that history is
recomputed from snapshots.
