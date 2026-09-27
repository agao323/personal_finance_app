# 077 — Record a partial amount for any period
Status: done
Wave: 7   Lane: —
Blocked by: none
Read first: none

## Goal
A partial use can be recorded against a past period, not only the current one.

## Acceptance criteria
- [ ] The period grid carries a control that takes a period and an amount, listing the
      periods currently shown by their own labels.
- [ ] It records a new partial use and corrects an existing one, including a period already
      marked at full value. `POST /perks/{id}/redemptions` is already idempotent and updates
      the amount when one is given, so no endpoint changes.
- [ ] The chip updates in place, showing the amount, without the grid rebuilding.
- [ ] One tap on a chip still records the full value. The fast path does not get slower to
      make room for the rare one.
- [ ] Tests: component — a partial amount against a past period posts that period's start and
      the amount; correcting a full mark to a partial one posts the same period; the chip
      shows the amount afterwards.

## Files
- `web/src/components/cards/period-grid.tsx`
- `web/src/components/cards/period-grid.test.tsx`

## Notes
`MarkButton` has had a "Part" control since 053, but only ever for the current period, so a
credit you half-used in March could be recorded as all or nothing and no more.

A separate control rather than a second gesture on the chip: tapping a used chip un-marks it,
which is the common correction, and putting an amount editor behind that tap would make undo
a two-step operation to serve the rarer case.
