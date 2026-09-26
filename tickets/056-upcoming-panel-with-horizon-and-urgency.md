# 056 — Upcoming credits: a horizon you choose, urgency that knows the cadence
Status: todo
Wave: 7   Lane: W2
Blocked by: 054
Read first: tickets/053-card-perks-schema-for-partial-use-and-fees.md

## Goal
Replace the fixed 45-day band with a list you can scope, where "urgent" means something
different for a monthly credit than an annual one.

## Acceptance criteria
- [ ] A horizon control — 30 / 90 / 180 days / everything — passed to
      `GET /perks/upcoming` as `within_days`. Default 90, so an annual credit is visible
      without being asked for
- [ ] Ordered soonest-first, and **urgent items are visually distinct** using the API's
      `is_urgent`, not a threshold recomputed here. One rule, one place
- [ ] Urgency is never colour alone — an icon or label too, per the existing `StaleBadge`
      precedent
- [ ] Each row names the card it belongs to. A credit without its card is not actionable
- [ ] The total value at stake, and the urgent subtotal separately
- [ ] Marking used from this panel, optimistically, reverting visibly on failure
- [ ] A selected horizon survives a reload (`localStorage`, wrapped in try/catch — it
      throws outright in some contexts)
- [ ] Tests: the horizon changes the request; urgent styling follows the API flag and not
      a local calculation; ordering; an empty horizon says so without reading as an error

## Files
- `web/src/components/cards/upcoming.tsx`
- `web/src/components/cards/upcoming.test.tsx`

## Notes

**Do not recompute urgency in the browser.** `services/perks.is_urgent` is the one
implementation; a second one in TypeScript would drift, and the symptom would be a credit
the page called safe and the API called urgent.

Monthly credits will dominate any list long enough to be useful. Grouping or a subtle
cadence label is in scope; a separate tab per cadence is not — that is the fragmented view
this panel exists to replace.
