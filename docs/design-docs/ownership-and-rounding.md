# Ownership and rounding

The requirement that makes this more than a spreadsheet: *if I own 50% of an asset, only
50% counts toward my net worth.* Same for liabilities. Everything here exists to make that
number right on every date, including past ones.

Decided in [DECISIONS.md](../DECISIONS.md) (2026-08-14, "Household, not single user" and
"Money is 2 decimal places, and rounding happens once"). Code: `api/app/services/ownership.py`.

## `users`

```
id, email, display_name, is_active
```

One household, two users at most, ever ([PRODUCT.md](../PRODUCT.md#explicit-non-goal-scale)).
The second row is a partner: add the member on the household screen, and add their email
to the Cloudflare Access policy. That is the whole procedure — no invitation, no roles, no
sharing UI. Miss the Access step and they never reach the origin, which from their side is
indistinguishable from being refused. See [product-specs/household-members.md](../product-specs/household-members.md).

**The `users` table is also the auth allowlist** — there is no separate allowlist config.
Cloudflare Access authenticates; `users` authorises ([SECURITY.md](../SECURITY.md#auth)).

**Deactivate, never delete.** `ownership_stakes.owner_user_id` is `ON DELETE RESTRICT`: a
stake is a historical fact, and deleting the user it points at would silently rewrite past
net worth. `current_user` reads `is_active` on every request, so deactivation takes effect
on the next one.

Why a `users` table existed from the first migration when v1 had one user: the original
plan had `ownership_stakes.owner` with no definition of whose stake counted — a hole in the
load-bearing calculation. Building it up front was one ticket; retrofitting it would have
meant changing every service signature and endpoint and backfilling user ids into a
database already holding real data.

## `ownership_stakes`

```
account_id, owner_user_id → users.id, percentage, effective_from, effective_to (nullable)
```

**Every account gets an explicit 100% stake row when it is created**
(`ownership.create_initial_stake`, called without exception). There is no implicit "an
account with no stake row is fully owned" default — with two possible owners that default
is ambiguous, and removing it deletes a special case from the lookup helper rather than
adding one. `effective_stake` returns `None` for "held no stake that day", which excludes
the account rather than zeroing it.

**Effective-dated.** A stake that changes on 2027-03-01 closes the old row and opens a new
one (`transition_stake`, both writes in one transaction). Without this, changing a stake
silently rewrites your historical net worth — the charts would retroactively lie. It cost
almost nothing up front and could not have been added cheaply later, because the history it
needs would never have been recorded.

**Half-open ranges**, `[effective_from, effective_to)`: the day a stake changes belongs to
the new row, and closing one the same day another opens leaves neither a gap nor an
overlap. A change dated at or before a stake's own start replaces it rather than closing it
into a zero-length range.

**Invariant:** for any account, stakes overlapping any given date sum to ≤ 100%. Enforced by
`_assert_within_limit` against every overlapping row (not just the start date — a stake
spanning years can collide with a short one anywhere inside it), by
`ck_stakes_percentage_range` (`0 < percentage ≤ 100`) and `ck_stakes_date_order`, and tested
by `test_ownership.py`, including `test_invariant_holds_across_generated_histories`.

Percentages are `NUMERIC(5,2)` in Postgres and **integer basis points** on the wire
(`5000` = 50.00%). 33.33 as a double is 33.329999999999998, and a three-way split is real.

## Visibility: household-shared

Both users see every account. Only the *money* splits:

- `net_worth(as_of, viewer_id)` returns that user's ownership-adjusted share.
- `net_worth(as_of, viewer_id=None)` returns the household total across all stakes.
- The dashboard has a **Mine / Household** toggle. That is the entire multi-user surface.

Household is always ≥ Mine — it sums a superset of your stakes — with strict inequality
once a partner holds anything (the seed asserts both; ticket 040).

Per-account privacy was rejected: it means filtering every query by viewer, which is a
multi-tenancy tax on an app that will never have tenants.

**Spend and runway are per-account and are never fractionally attributed by ownership.** A
$60 grocery charge on a jointly-owned card is $60 of spend, not $30. Splitting spend by
ownership stake is a rabbit hole with no correct answer, and it isn't what the number is
for. (Runway's *liquid assets* side is ownership-adjusted; its *burn* side is not.)

## Ownership is applied in exactly one place

**Every** net worth figure is ownership-adjusted. The adjustment — and the rounding it
implies — happens in `ownership.adjust()`, and everything calls it: net worth, the series,
runway's liquid total, and the accounts list's adjusted values. If you find yourself
writing `SUM(balance)` for a net worth figure, stop.

`api/tests/test_architecture.py` enforces the mechanical half: no multiplication or
division involving a percentage or stake outside `services/ownership.py`.

**The stake *lookup* has two implementations, pinned together.** Ticket 052 fixed an N+1 in
the series by loading every stake once and resolving them in memory
(`net_worth._ledger_percentage`, "the in-memory twin" of `effective_stake` /
`household_stake`). It still applies stakes through `adjust`. Because two implementations of
one rule drift, `test_net_worth_series.py::test_the_series_agrees_with_the_single_date_calculation`
and `test_the_series_agrees_on_contributions_too` assert the series equals the single-date
calculation point by point.

**Raw sums exist, but never as net worth.** The accounts list shows raw and adjusted
subtotals side by side per group — the point of ticket 019 is that a 50%-owned asset
visibly shows both. `AccountList.total_cents`, though, sums raw balances across kinds (a
mortgage plus a brokerage) and means nothing; the UI does not show it. That is debt, not
design: [tech-debt-tracker.md](../exec-plans/tech-debt-tracker.md).

## Money

`Decimal` in Python, `NUMERIC(19,2)` in Postgres, **integer cents** over the wire. Never
float, anywhere, for any reason. `scripts/check_no_float.sh` fails the build if `Float`,
`REAL`, `DOUBLE_PRECISION` or `Mapped[float]` appears in a column definition, and
`test_contract.py` fails if any schema field is a float (one display ratio excepted).

Two decimal places everywhere is deliberate. Balances are dollars and cents; the extra
precision would be spurious for a number that changes daily anyway, and 2dp storage
round-trips exactly through integer cents, so the wire format needs no scale field and no
decimal strings. The original plan's `NUMERIC(19,4)` did not round-trip: `1234.5678`
became `123457` cents and back to `1234.5700`.

If holdings-level tracking (shares × price) is ever added, prices need their own precision —
2dp is correct for balances and wrong for unit prices. That's a Later concern, called out so
nobody assumes 2dp generalises.

The browser parses money by splitting the string, never by multiplying:
`parseFloat("12.34") * 100` is `1233.9999999999998`. See [FRONTEND.md](../FRONTEND.md).

## Rounding

Ownership math produces fractional cents — 50% of $1,234.57 is $617.285. The rule:

> **Round half-up, per account, immediately after applying the stake. Then sum.**

Rounding per account rather than on the total means the figure on screen always equals the
sum of the rows above it. Rounding at the end produces a dashboard where the numbers visibly
don't add up, which destroys trust in every other number on the page. Half-up rather than
Python's default banker's rounding: a household reading a statement expects $617.29, and
$617.28 would be unexplainable.

`ownership.adjust()` is the only place ownership-adjusted money is rounded. Its companion
`ownership.split()` divides an already-rounded figure — an account's balance by asset class
(ticket 116) — by largest remainder, so the parts sum exactly to it and nothing is rounded twice.
Neither is the only `quantize` in the codebase, and an earlier version of this doc said it was:

| Where | What | Why it is not a second rounding of net worth |
|---|---|---|
| `schemas/common.py` `from_cents`, `from_bps` | wire → `Decimal` | Exact conversions; nothing is lost |
| `services/csv_import.py` | normalises parsed amounts to 2dp | Input validation; a file whose amounts don't round-trip is refused (ticket 020) |
| `services/runway.py` | the trailing-average burn, half-up | A display figure derived from spend, never summed into net worth |
| `web/src/lib/format.ts` `parseDollarsToCents` | a typed half cent rounds away from zero | Matches `ROUND_HALF_UP` so the browser and server agree (ticket 031) |
| `services/analysis/numbers.py` | derived figures that divide — averages, shares, projections — half-up, once, at the edge | Never summed into net worth; the rounding site for derived figures ([ADVISOR.md](../ADVISOR.md#numbers)) |
| `services/analysis/debt.py` | a schedule's interest, to the cent every month, half-up | What a lender's statement does; the one figure rounded more than once, on purpose (ticket 115) |
