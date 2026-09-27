# 068 — List a perk's recent periods
Status: done
Wave: 7   Lane: —
Blocked by: none
Read first: docs/ARCHITECTURE.md#card_perks--perk_redemptions

## Goal
`GET /perks/{perk_id}/periods` returns the last N periods of one perk, oldest first, each
with whether it was used. The screen can then offer "which months did you use this?"
instead of asking for a date and explaining which period that date lands in.

## Acceptance criteria
- [ ] `services/perks.period_at(cadence, anchor_on, index)` builds a period from its index,
      and `recent_periods(cadence, anchor_on, on, count)` returns the `count` periods
      ending with the one containing `on`, oldest first.
- [ ] `recent_periods` returns `[]` when `on` is before `anchor_on`, and fewer than `count`
      periods when the perk has not existed that long. Never a period before index 0.
- [ ] `GET /perks/{perk_id}/periods?back=N&on=DATE` returns `PerkPeriodsRead`: the perk's
      cadence and anchor, the periods, and `has_earlier` so the browser knows whether a
      "show earlier" control has anything to show.
- [ ] Each period carries `start`, `end`, `index`, `is_used`, `used_amount_cents`, `note`,
      `is_current`.
- [ ] One query for the redemptions in the returned range, not one per period.
- [ ] `make types` run and the regenerated `api-types.ts` committed.
- [ ] Tests: unit — `period_at` round-trips with `period_containing` for a month-end anchor
      across a February; `recent_periods` at an anchor boundary, one day before it, and
      with `count` larger than the perk's age. Functional — a perk with two recorded
      periods reports exactly those two as used; `has_earlier` false at the anchor and true
      beyond it; 404 for an unknown perk.

## Files
- `api/app/services/perks.py`
- `api/app/schemas/card_perk.py`
- `api/app/routers/cards.py`
- `api/tests/test_perks_service.py`, `api/tests/test_cards_router.py`
- `web/src/lib/api-types.ts` (generated)

## Notes
The period arithmetic stays in `services/perks.py`. A TypeScript reimplementation of
`add_months` and its day-of-month clamping is exactly the second implementation the module
docstring exists to prevent, and it would disagree on a perk anchored on the 31st.

`back` is a plain count, not a date span: how much history is worth showing is a per-cadence
question the browser answers (12 months, 8 quarters, 4 halves, 3 years), and the API should
not carry that policy.
