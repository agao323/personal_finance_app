# 051 — Card perks: the screen
Status: todo
Wave: 6   Lane: —
Blocked by: 050
Read first: tickets/050-card-perks-api.md

## Goal
A page that opens with what is about to expire, and lets a perk be marked used in one
click.

## Acceptance criteria
- [ ] `/cards` — **expiring first**, then cards with their perks
- [ ] Each perk shows its value, what period it is in, when that period ends, and a
      single control to mark used or undo
- [ ] Marking is optimistic and reverts visibly if the request fails. This is a button
      that gets pressed on a phone in a restaurant; a spinner blocking the row is worse
      than a wrong state for 200ms that corrects itself
- [ ] Add and edit a perk: name, value, cadence, anchor date
- [ ] **The anchor date field explains itself.** "Anchor date" is meaningless without
      the sentence that follows it: the date this perk's first period began — 1 January
      for a calendar-year credit, or the day the card was opened for one that resets on
      the cardmember year. Nobody will guess that from a label
- [ ] The total value of unused perks expiring soon, stated plainly
- [ ] Nav entry
- [ ] Tests: the expiring list renders and orders correctly, marking calls the API and
      updates the row, a failed mark reverts, and the add form validates

## Files
- `web/src/app/(dashboard)/cards/page.tsx`
- `web/src/app/(dashboard)/cards/page.test.tsx`
- `web/src/components/nav.tsx`
- `web/src/test/msw.ts`

## Notes

**Money renders from integer cents** through the existing formatter. Do not divide by
100 in the component.

**No card artwork, no issuer logos, no annual-fee break-even calculator.** One
household, prefer boring — the ask was to stop losing track of perks.
