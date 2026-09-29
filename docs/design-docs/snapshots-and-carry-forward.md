# Snapshots and carry-forward

## `balance_snapshots`

```
account_id, as_of (date), balance, source     -- unique (account_id, as_of)
```

Aggregators return *current* balances; essentially nobody backfills years of history.
Which means: **history that isn't captured is lost permanently.** Snapshots started on
first deploy, and **every balance write appends one** — through
`services/balances.record_balance`, never directly to the table.

"Net worth over time" is a derived view over this table. It is not computable any other
way. The Google Sheet import ([sheet-import](../product-specs/sheet-import.md)) exists to
seed this table with the history that predates the app, and writes through the same
function.

**Current balance is derived** as the latest snapshot, never duplicated onto `accounts`.
Duplicating it would create a second source of truth that can disagree with the history,
and the disagreement would be invisible until a chart looked wrong. Accept the join.

**One row per account per date.** `record_balance` upserts on `(account_id, as_of)`, so a
second write on the same day corrects that day rather than duplicating it, and
out-of-order writes resolve by date, not insertion order (`test_balances.py`).

**This is the one irreplaceable table.** Banks do not serve historical balance-at-a-date,
and for 401k, HSA, brokerage, property and vehicle values nobody does. Everything else in
the database is reconstructible from bank CSVs or a few hand-typed rows, which is what let
backups get smaller ([ADR 0008](../adr/0008-local-backups.md)).

## Closed accounts and carry-forward

You will not snapshot every account every day, so a net worth series has to carry the
last known balance forward. Carry-forward without a close date is a correctness bug: sell
the car, stop updating the account, and its final balance sits in your net worth forever.
Same for a paid-off loan or a rolled-over 401k.

Two mechanisms, both required:

- **`closed_at`** — an account is excluded from any `as_of` at or after its close date.
  Closing keeps the history and the transactions; it is not deletion.
- **A 90-day staleness cap** (`balances.STALE_AFTER`, roughly a quarterly statement
  cycle) — past that the account still counts, but the value is flagged stale in the API
  response (`stale_account_ids` on `/net-worth`, `stale_account_count` per series point,
  `is_stale` per account) and surfaced in the UI as a prompt to update it. Flagged, not
  dropped: dropping a stale balance would make net worth jump for a bookkeeping reason.

Two more rules, both from ticket 013:

- An account with **no snapshot on or before `as_of` is excluded, not treated as zero.**
  Zero would claim a balance nobody recorded — and for a sheet import, a blank cell means
  the account did not exist yet, not that it was empty (ticket 024).
- **"In force on `as_of`" means that date's balances *and* that date's stakes.** If a past
  point used today's stakes, every point on the chart except the last would be wrong, and
  it would look plausible.

## Known gap

The series reports `stale_account_count` for every point (added in 014 at 027's request),
but no chart reads it, so a flat stretch built from a year-old balance is drawn as if it
were measured. Tracked in [tech-debt-tracker.md](../exec-plans/tech-debt-tracker.md).

## Where it is tested

`api/tests/test_balances.py` (write path, carry-forward, the cap at exactly 90 days and one
day past it, close dates), `test_net_worth.py` (hand-computed values across a stake change,
a closed account, a stale snapshot, a missing snapshot), `test_net_worth_series.py` (the
series agrees with the single-date calculation, and the query count does not grow with the
range).
