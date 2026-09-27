# ADR 0013 — Asset allocation is recorded per account, not per holding

Status: proposed · 2026-09-27 · Ticket 080

## Context

"What's my asset allocation?" and "am I on track to retire?" both need to know what the money is
invested in. Today the app knows an account's `kind` and `subtype`, which gives liquid vs illiquid
and nothing about equities vs bonds.

PRODUCT already lists holdings-level tracking as Later: *shares × price, which would require a
second precision regime*. ARCHITECTURE makes the same point: balances are 2dp; unit prices are
not.

## Decision

**Record allocation per account as percentages by asset class, effective-dated like ownership
stakes.**

```
account_allocations
  account_id, asset_class (us_equity | intl_equity | bonds | cash | real_estate | other),
  percentage NUMERIC(5,2), effective_from, effective_to
  -- rows in force on any date sum to exactly 100 per account
```

- Cash accounts, property and vehicles derive their class from `subtype`, and are marked derived.
- An investment account with no rows reports its share as **unknown**. It is never guessed.
- A class's value is the account's ownership-adjusted balance split by the percentages, using a
  largest-remainder helper **in `services/ownership.py`**, so the classes sum exactly to the
  account's figure and rounding still happens in one place.

## Alternatives considered

**Holdings: shares × price.** The accurate version, and the expensive one. Unit prices need their
own precision and their own storage. Prices need a source: a market-data feed is an outbound
fetch, which the advisor's constraints rule out for the API; entering prices by hand every month
is a chore that decays. Lots, splits and fund mergers follow. All of it to answer a question —
asset mix — that percentages answer to within what matters.

**Derive allocation from `subtype`.** Free, and wrong where it matters most: a 401k can be 100%
equities or 100% stable value, and a brokerage account can hold anything.

**A single household-level allocation.** One set of percentages for everything. Simple, and it
cannot say which account to rebalance in, or treat a tax-deferred account differently from a
taxable one, which the FIRE projections need.

## Consequences

**Easy.** Two to five numbers per investment account, set once and touched on a rebalance. The
balances already snapshotted do the rest. The 2dp regime is untouched. Drift from a target and
cash drag become straightforward analyses.

**Hard.** It goes stale silently: markets move the real mix away from what was entered. The
allocation carries an `effective_from` date, and the advisor states it ("as entered on 3 March").
A target-date fund's glide path is not modelled; its percentages are whatever was last entered.

**Foreclosed, for now.** Per-security questions: cost basis, tax-loss harvesting, a fund's expense
ratio. The advisor records these as a `holdings` limitation, and a count of how often that comes
up is the evidence for reopening this decision.
