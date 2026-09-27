# 079 — Credits reset on calendar boundaries unless you say otherwise
Status: done
Wave: 7   Lane: —
Blocked by: none
Read first: docs/ARCHITECTURE.md#card_perks--perk_redemptions

## Goal
A quarterly credit resets on 1 January, 1 April, 1 July and 1 October, because that is what
"quarterly" means on a credit card. Getting anything else requires saying so, and the form
shows the reset dates before you save.

## Acceptance criteria
- [ ] Adding a credit defaults its anchor to 1 January of the current year, which is
      calendar-aligned at every cadence: months from the 1st, quarters at Jan/Apr/Jul/Oct,
      halves at Jan/Jul, and the calendar year.
- [ ] The form offers "Calendar quarters" (named for the chosen cadence) or "A different
      date", and only the second reveals a date input.
- [ ] `services/perks.is_calendar_aligned(cadence, anchor)` is the one definition of aligned:
      day 1, and `(month - 1) % MONTHS[cadence] == 0`.
- [ ] `GET /perks/schedule?cadence=&anchor_on=&on=` returns the current period's start, the
      next reset dates, and whether the anchor is calendar-aligned.
- [ ] The form shows the next reset dates live as cadence or anchor changes, **from that
      endpoint**, never from arithmetic in the browser.
- [ ] A non-aligned anchor is stated plainly in the form rather than merely permitted, since
      it is right for a cardmember-year credit and wrong by accident the rest of the time.
- [ ] `make types` run and the regenerated `api-types.ts` committed.
- [ ] Tests: unit — `is_calendar_aligned` across all four cadences and every month, including
      a day other than the 1st. Functional — the schedule for a quarterly credit anchored
      1 September reports 1 December and is not aligned; anchored 1 January it reports
      1 October and is. Component — the default produces calendar quarters; choosing a
      different date reveals the input; the preview renders the endpoint's dates.

## Files
- `api/app/services/perks.py`
- `api/app/routers/cards.py`, `api/app/schemas/card_perk.py`
- `web/src/components/cards/perk-form.tsx`
- `api/tests/test_perks.py`, `api/tests/test_cards.py`
- `web/src/components/cards/perk-form.test.tsx`
- `web/src/lib/api-types.ts` (generated)

## Notes
No arithmetic bug. Periods step from the anchor by the cadence, and every anchor produces
correct boundaries — anchored 1 September, a quarterly credit genuinely does reset on
1 December. The defect is that the anchor was a free date field with no default and no
visible consequence, so the value people reach for is the day they added the credit here.

This is the third symptom of the same cause. 076 was a monthly credit anchored 13 August
offering two chips; before that the field's hint invited "the day you opened the card". The
anchor is a real and necessary control — a credit that resets on your cardmember year needs
it — but it is a sharp default, and the fix is to stop asking for it by default and to show
what it does when it is asked for.

The preview comes from the API for the same reason the grid's periods do: a second
implementation of the period arithmetic in TypeScript would disagree eventually, and this one
would disagree in the form that sets it.

Existing credits keep their anchors. Editing one to be calendar-aligned is a single field,
and the form already warns that recorded history stays attached to the periods it was
recorded against.
