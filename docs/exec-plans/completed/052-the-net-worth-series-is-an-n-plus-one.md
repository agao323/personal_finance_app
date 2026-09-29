# 052 — The net worth series issues thousands of queries
Status: done
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
- [x] The series loads accounts, snapshots and stakes **once** and walks the dates in
      memory. Query count is bounded and independent of the number of points
- [x] **`net_worth()` is not touched.** It is one date, its cost is fine, and it is what
      `/net-worth`, the export, and every other caller use. Rewriting it to share the new
      path would put the most important number in the app at risk for a chart's benefit
- [x] **A test asserts the two agree**, point for point, over a fixture with a part-owned
      account, a mid-history stake change, a closed account, and a stale balance. This is
      the criterion that matters: the risk here is a *second* implementation of the
      ownership and carry-forward semantics that drifts from the first, and the only real
      protection is a test that fails when it does
- [x] A test asserts the query count stays bounded — a fixed small number for a long
      range, so a future change that reintroduces a per-point query fails loudly rather
      than getting slower quietly
- [x] Rounding still happens exactly once per account in `services/ownership.py`. The
      new path calls `adjust()` the same way; it must not sum raw balances
- [x] Carry-forward, the 90-day staleness cap, closed-account exclusion, and
      "no stake that day means excluded, not zero" all behave identically
- [x] The chart caches by `view|range`, so switching back to a range already loaded does
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

## Done — 2026-08-26

| Range | Before | After |
|---|---|---|
| 3M day (91 points) | 1,548 queries, 0.46s | **4 queries, 0.062s** |
| 6M day (183 points) | 3,112 queries, 0.76s | 4 queries, 0.007s |
| 1Y day (366 points) | 6,479 queries, 1.58s | 4 queries, 0.012s |
| 1Y week (54 points) | 957 queries | 4 queries |

Four queries whatever the range: `earliest_snapshot`, accounts, snapshots, stakes. Local
timings understate the win — in production each of those was a round trip to Neon.

**`net_worth()` was not touched**, and that was the point. It is what `/net-worth`, the
export and the dashboard headline use, and rewriting it to share the new path would have
put the most important number in the app at risk for a chart's benefit. The only thing
the two now share is `_total`, so they cannot disagree about how contributions roll up.

**The real work here was the safety net, not the speed.** Loading once means a second
reading of carry-forward, the staleness cap, closed-account exclusion, and half-open
stake ranges. `test_the_series_agrees_with_the_single_date_calculation` computes both ways
across three viewers × three intervals over eight months of deliberately awkward history —
a part-owned account, a stake that changes mid-history, an account that closes, one that
opens late, one that goes stale — and asserts they match point for point, contributions
included.

I mutation-tested it rather than trusting it: flipping the in-memory stake range from
half-open to inclusive makes it fail. Notably the **weekly** interval did *not* catch that
mutation and the daily one did, because the changed boundary fell between weekly points —
which is the argument for the interval matrix rather than one representative case.

The tripwires are there for the same reason as the contract test's: `assert len(series) ==
len(expected)` passes when both are empty, and this session has already shipped one
vacuously-passing guard.

**The client cache went in as state, not a ref.** The first version wrote a `useRef` cache
during render — idempotent and, I thought, tidy. `react-hooks` rejects ref access during
render outright, so it moved to state written only from a settled response. Disabling the
short-circuit fails four tests.

Guards 19, API 483, web 418.
