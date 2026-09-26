# 053 — Schema and services for partial use, fees, and cadence urgency
Status: todo
Wave: 7   Lane: —
Blocked by: none
Read first: tickets/049-card-perks-schema-and-period-engine.md

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
- [ ] `perk_redemptions.amount` — nullable money. `NULL` means "used, full face value",
      which is what a one-tap mark records. A value means partial. Never zero: a zero
      redemption is an unused period, and there is already a way to express that — no row
- [ ] `accounts.annual_fee` and `accounts.fee_renews_on`, both nullable. Credit-card only
      in practice; documented as such rather than constrained, because Postgres cannot
      cheaply enforce "only when subtype = credit_card" and a side table for two columns
      buys a join and nothing else
- [ ] `services/perks.py` gains `URGENT_WITHIN`: monthly 7 days, quarterly 14,
      semiannual 21, annual 30 — and an `is_urgent(cadence, days_remaining)` helper.
      **One table, no configuration.** 30 days is noise on a monthly credit and too late
      on an annual one, which is the whole reason the threshold varies
- [ ] `Period.days_remaining` is unchanged and still 0 on the last day. Urgency reads it
- [ ] Money stays `Decimal` / `NUMERIC(19,2)`, integer cents on the wire
- [ ] Hand-written migration, human-reviewed, with a downgrade that recreates indexes
- [ ] Tests: the amount constraint refuses zero and negative; `is_urgent` at each
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
