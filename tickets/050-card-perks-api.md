# 050 — Card perks: the API
Status: todo
Wave: 6   Lane: —
Blocked by: 049
Read first: tickets/049-card-perks-schema-and-period-engine.md

## Goal
Endpoints to manage perks and mark them used, plus the one read that answers the actual
question: **what have I not used yet, and when does it expire?**

## Acceptance criteria
- [ ] `GET /cards` — credit-card accounts with their perks, each carrying the **current
      period**, whether it is used, and the period's end date
- [ ] `POST /cards/{account_id}/perks`, `PATCH /perks/{perk_id}`, and retire a perk
      without deleting it
- [ ] `POST /perks/{perk_id}/redemptions` marks the period containing a given date as
      used; `DELETE` unmarks it. Both are idempotent — marking twice is not an error,
      because the button will be pressed twice
- [ ] The date is a **parameter, defaulting to today**, never `date.today()` read inside
      the service. Every test that matters here is about a specific date, and a function
      that reads the clock cannot be tested for "the day the period rolls over"
- [ ] `GET /perks/upcoming?within_days=N` — unused perks whose period ends within the
      window, soonest first, with the total value at stake. This is the endpoint the
      request was actually about
- [ ] Money as **integer cents** over the wire, per CLAUDE.md
- [ ] A perk on an account that is closed, or not a credit card, is refused
- [ ] Tests: functional coverage of marking and unmarking, marking twice, a redemption
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
