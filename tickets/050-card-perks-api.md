# 050 — Card perks: the API
Status: done
Wave: 6   Lane: —
Blocked by: 049
Read first: tickets/049-card-perks-schema-and-period-engine.md

## Goal
Endpoints to manage perks and mark them used, plus the one read that answers the actual
question: **what have I not used yet, and when does it expire?**

## Acceptance criteria
- [x] `GET /cards` — credit-card accounts with their perks, each carrying the **current
      period**, whether it is used, and the period's end date
- [x] `POST /cards/{account_id}/perks`, `PATCH /perks/{perk_id}`, and retire a perk
      without deleting it
- [x] `POST /perks/{perk_id}/redemptions` marks the period containing a given date as
      used; `DELETE` unmarks it. Both are idempotent — marking twice is not an error,
      because the button will be pressed twice
- [x] The date is a **parameter, defaulting to today**, never `date.today()` read inside
      the service. Every test that matters here is about a specific date, and a function
      that reads the clock cannot be tested for "the day the period rolls over"
- [x] `GET /perks/upcoming?within_days=N` — unused perks whose period ends within the
      window, soonest first, with the total value at stake. This is the endpoint the
      request was actually about
- [x] Money as **integer cents** over the wire, per CLAUDE.md
- [x] A perk on an account that is closed, or not a credit card, is refused
- [x] Tests: functional coverage of marking and unmarking, marking twice, a redemption
      landing in the right period for a date near a boundary, `upcoming` ordering and
      totals, and the refusals

## Files
- `api/app/routers/cards.py`
- `api/app/schemas/card_perk.py`
- `api/app/main.py`
- `api/tests/test_cards.py`

## Contract change

Additive — new routes and schemas. Run `make types` and commit the regenerated file.

## Notes

**`upcoming` is the feature.** The rest is data entry. A list of cards and perks that
required reading down it to work out what is about to expire would be a worse version of
the spreadsheet this replaces.

**Do not compute "used" from a redemption's presence at read time in the route.** It goes
through `services/perks.py`, so there is exactly one place that decides what period a
date is in — the same rule as rounding living only in `services/ownership.py`.

## Done — 2026-08-26

**The rollover test is the one that earns its place.** A monthly perk marked on
31 December is spent for December and available again on 1 January. If that were wrong
nobody would notice for a month, and by then the wrong answer would look like the
history.

**Marking is idempotent in both directions.** Marking twice is a no-op rather than a
409, and unmarking something never marked is a no-op rather than a 404. The alternative
is answering an error to a button that was pressed twice because the first tap did not
visibly do anything, which is the situation this is actually for.

`current_period` is `null` for a perk whose anchor is in the future, and that is
deliberately different from an unused period. "Has not started" and "available" are not
the same state, and collapsing them would put a perk you cannot use yet into the list of
things about to expire.

**One thing I wrote badly and fixed:** `update_perk` first tried to assign `value_cents`
onto the model and then delete the attribute again. `value_cents` is the wire name and
the column is `value`, holding a `Decimal` — it is popped from the payload and converted
once, so there is no path where an integer number of cents reaches a money column. There
is a test asserting the stored value reads `123.45`.

Contract re-freeze is additive: +526 lines, no removals.

480 passed.
