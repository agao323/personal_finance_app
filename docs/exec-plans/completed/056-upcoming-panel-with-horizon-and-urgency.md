# 056 — Upcoming credits: a horizon you choose, urgency that knows the cadence
Status: done
Wave: 7   Lane: W2
Blocked by: 054
Read first: docs/exec-plans/completed/053-card-perks-schema-for-partial-use-and-fees.md

## Goal
Replace the fixed 45-day band with a list you can scope, where "urgent" means something
different for a monthly credit than an annual one.

## Acceptance criteria
- [x] A horizon control — 30 / 90 / 180 days / everything — passed to
      `GET /perks/upcoming` as `within_days`. Default 90, so an annual credit is visible
      without being asked for
- [x] Ordered soonest-first, and **urgent items are visually distinct** using the API's
      `is_urgent`, not a threshold recomputed here. One rule, one place
- [x] Urgency is never colour alone — an icon or label too, per the existing `StaleBadge`
      precedent
- [x] Each row names the card it belongs to. A credit without its card is not actionable
- [x] The total value at stake, and the urgent subtotal separately
- [x] Marking used from this panel, optimistically, reverting visibly on failure
- [x] A selected horizon survives a reload (`localStorage`, wrapped in try/catch — it
      throws outright in some contexts)
- [x] Tests: the horizon changes the request; urgent styling follows the API flag and not
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

## Done — 2026-09-26

Split into **Running out** and **Plenty of time**, both driven by the API's `is_urgent`.
There is a test that feeds the panel a credit with 3 days left and `is_urgent: false` and
asserts it lands in "plenty of time" — if the component recomputed a threshold locally it
would disagree with the server, and that test is what makes the single-implementation rule
enforceable rather than aspirational.

Default horizon is 90 days. 45 hid annual credits entirely, which was half the original
complaint; the other half was a monthly credit shouting for most of its life, which the
cadence table in 053 fixes.

The horizon is read from `localStorage` via a **lazy `useState` initialiser**, not in an
effect. Reading it in an effect and calling `setState` is a synchronous setState inside an
effect — the `react-hooks` rule I had already tripped once on this page — and the lazy form
also avoids a wasted render. `storedHorizon` returns the default whenever the store is
unreadable, which covers a server render and a private window alike.
