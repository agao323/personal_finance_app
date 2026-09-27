# 076 — A credit's anchor sets phase, not a start date
Status: done
Wave: 7   Lane: —
Blocked by: none
Read first: docs/ARCHITECTURE.md#card_perks--perk_redemptions

## Goal
The period grid covers a full year whatever date a credit was set up with. Today it stops at
`anchor_on`, so a monthly credit anchored 13 August 2026 offers exactly two chips and no way
to record the eight months before it.

## Acceptance criteria
- [ ] `period_at` accepts a negative index; `recent_periods` no longer clamps at zero;
      `period_containing` always answers and its return type stops being optional.
- [ ] `POST /perks/{id}/redemptions` no longer refuses a date before the anchor with 422.
- [ ] A perk whose anchor is in the **future** still reports `current_period: null`, decided
      by the caller comparing the anchor to the evaluated date rather than by
      `period_containing` returning `None` for two different questions.
- [ ] `has_earlier` is always true, and says so in the schema: there is no first period any
      more. The client's own cap on `back` is what ends "show earlier".
- [ ] A test asserts each cadence's `PERIODS_BACK` covers every period of the current
      calendar year on any date in it, so the constants cannot drift out from under the
      promise.
- [ ] The perk form stops calling the field "First period began" and stops telling you to
      enter the day you opened the card as though history began there.
- [ ] `missed_periods` still counts from the anchor, not from the beginning of time.
- [ ] Tests: unit — `add_months` across a negative span and a year boundary; `recent_periods`
      returning periods before the anchor with correct boundaries for a month-end anchor.
      Functional — a period before the anchor can be marked and reads back as used.

## Files
- `api/app/services/perks.py`
- `api/app/routers/cards.py`
- `api/app/schemas/card_perk.py`
- `web/src/components/cards/perk-form.tsx`
- `api/tests/test_perks.py`, `api/tests/test_cards.py`

## Notes
The clip was deliberate: "a date before the anchor is not period -1, it is a question about a
perk that did not exist yet, and returning a window for it would let a redemption be recorded
against a period that never happened."

That reasoning assumed `anchor_on` records when the credit came into existence. It does not.
It records when *a* period began, and in practice people enter the day they set the credit up
in this app — which the field's own hint invited by saying "the day you opened the card".
Treating that as the beginning of history means the app refuses to record a use it has no
reason to doubt.

So the anchor keeps its real job — deciding where a boundary falls, which is what makes a
monthly credit reset on the 13th rather than the 1st — and loses the job it was never
reliable at.

The cost is that nothing now stops a use being recorded against 2019 on a card opened in
2026. That is the owner's own record of their own spending, and the grid only ever offers the
periods it was asked for.

`add_months` already handles negative spans correctly — Python floors division and modulo
toward negative infinity, so month −3 resolves to October of the previous year. Asserted
rather than assumed.
