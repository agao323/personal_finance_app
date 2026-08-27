# 051 — Card perks: the screen
Status: done
Wave: 6   Lane: —
Blocked by: 050
Read first: tickets/050-card-perks-api.md

## Goal
A page that opens with what is about to expire, and lets a perk be marked used in one
click.

## Acceptance criteria
- [x] `/cards` — **expiring first**, then cards with their perks
- [x] Each perk shows its value, what period it is in, when that period ends, and a
      single control to mark used or undo
- [x] Marking is optimistic and reverts visibly if the request fails. This is a button
      that gets pressed on a phone in a restaurant; a spinner blocking the row is worse
      than a wrong state for 200ms that corrects itself
- [x] Add and edit a perk: name, value, cadence, anchor date
- [x] **The anchor date field explains itself.** "Anchor date" is meaningless without
      the sentence that follows it: the date this perk's first period began — 1 January
      for a calendar-year credit, or the day the card was opened for one that resets on
      the cardmember year. Nobody will guess that from a label
- [x] The total value of unused perks expiring soon, stated plainly
- [x] Nav entry
- [x] Tests: the expiring list renders and orders correctly, marking calls the API and
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

## Done — 2026-08-26

**The anchor-date field is the one that needed the most care and it is a hint, not a
label.** "First period began" is unguessable on its own, and a wrong anchor silently
shifts every period for that perk — no error, no empty state, just a reset date that is
quietly off by months. The hint spells out both cases, and there is a test asserting the
words "cardmember year" are on screen, because that sentence is load-bearing and would
otherwise be the first thing trimmed.

`expiryLabel` says **"Today"** rather than "0 days". `days_remaining` is 0 on the final
day — the API is explicit about that so this did not have to guess — and "expires in
0 days" is the sentence nobody parses at a glance, which is precisely the one that
matters most.

**Optimism only pays off if failure is visible**, so the failed-mark path is tested
directly: the button reverts and a "Did not save" alert appears beside it. A row that
stayed green after a failed write would be worse than no optimism at all.

Two mistakes of my own. The mark button first tried one `apiFetch` with a computed
`post | delete` method — the union narrows `body` to `undefined`, because DELETE takes
none, so the POST stopped type-checking. Two calls, less clever, compiles. And a test
asserted a banner had disappeared using a regex that also matched the empty state's
"**Nothing** expiring in the next 45 days" — an assertion that could never pass. It now
asserts the empty-state message directly, which is what it meant.

Web suite 27 files / 416 tests; guards 19.
