# 053 — Schema and services for partial use, fees, and cadence urgency
Status: done
Wave: 7   Lane: —
Blocked by: none
Read first: docs/exec-plans/completed/049-card-perks-schema-and-period-engine.md

## Goal
One migration carrying every schema change the card-page rebuild needs, plus the urgency
rule in `services/perks.py`. No API and no UI — this exists so 054 onward can run without
a second migration in flight.

## Why one ticket for two features

The repo allows **one in-flight migration at a time**. Splitting "partial redemption
amounts" and "annual fee" into separate tickets would serialise the whole wave behind two
migrations for four columns. They land together; the *features* built on them stay
separate tickets.

## Acceptance criteria
- [x] `perk_redemptions.amount` — nullable money. `NULL` means "used, full face value",
      which is what a one-tap mark records. A value means partial. Never zero: a zero
      redemption is an unused period, and there is already a way to express that — no row
- [x] `accounts.annual_fee` and `accounts.fee_renews_on`, both nullable. Credit-card only
      in practice; documented as such rather than constrained, because Postgres cannot
      cheaply enforce "only when subtype = credit_card" and a side table for two columns
      buys a join and nothing else
- [x] `services/perks.py` gains `URGENT_WITHIN`: monthly 7 days, quarterly 14,
      semiannual 21, annual 30 — and an `is_urgent(cadence, days_remaining)` helper.
      **One table, no configuration.** 30 days is noise on a monthly credit and too late
      on an annual one, which is the whole reason the threshold varies
- [x] `Period.days_remaining` is unchanged and still 0 on the last day. Urgency reads it
- [x] Money stays `Decimal` / `NUMERIC(19,2)`, integer cents on the wire
- [x] Hand-written migration, human-reviewed, with a downgrade that recreates indexes
- [x] Tests: the amount constraint refuses zero and negative; `is_urgent` at each
      cadence's boundary, the day either side of it, and on the final day

## Files
- `api/alembic/versions/0006_card_perk_amounts_and_fees.py`
- `api/app/models/card_perk.py`, `api/app/models/account.py`
- `api/app/services/perks.py`
- `api/tests/test_perks.py`

## Notes

**`NULL` amount means full value, deliberately.** The alternative — writing the perk's
face value into every redemption — would freeze a number that the perk can legitimately
change later, and then history would disagree with the perk it belongs to.

Nothing here touches net worth. An unused credit is still not an asset (049).

## Done — 2026-09-26

`URGENT_WITHIN` has a test asserting **every cadence has an entry**, because a fifth
cadence added later without one would raise `KeyError` on a live request rather than
failing a build. And `test_a_monthly_credit_is_not_urgent_for_most_of_its_life` pins the
actual complaint: at 20 days left a monthly credit is calm and an annual one is urgent.
The old fixed 45-day window got both backwards.

**`amount` is nullable and null means full value.** The alternative — writing the perk's
face value into every redemption — looked tidier and was wrong: a perk's value can change,
and history would then disagree with the perk it belongs to. The CHECK refuses zero, since
an unused period is already expressed by having no row.

`annual_fee` and `fee_renews_on` sit on `accounts` unconstrained by subtype. Postgres
cannot cheaply express "only when subtype is credit_card", and a side table for two columns
buys a join and nothing else. Documented in the model instead, including that net worth
must never read them — what a card costs to hold is not a balance.

The downgrade drops the columns and says outright that recorded partial amounts are lost.
A downgrade cannot preserve a value in a column it removes, and every affected redemption
reverts to meaning full face value.

494 passed.
