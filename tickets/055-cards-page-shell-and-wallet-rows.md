# 055 — Cards page: the shell and one row per card
Status: todo
Wave: 7   Lane: W1
Blocked by: 054
Read first: tickets/051-card-perks-screen.md

## Goal
The page structure, and a card row that shows a whole card's state without expanding it.

## Why the structure changes

Today the page leads with a single 45-day urgency band and then lists cards. Both
MaxRewards and Kudos do the opposite of the second half: **aggregate first, card second**,
because the question on opening is "what can I use", not "what does card three hold".
MaxRewards' Wallet row is the pattern worth taking — one row per card carrying its state
at a glance.

## Acceptance criteria
- [ ] `/cards` composes: the upcoming panel (056), then one row per card, then history
      (058). This ticket owns the composition and the row; the panels are slots
- [ ] A card row shows name, institution, perk count, **available value this period**, and
      a closed badge where relevant. Expanding reveals its perks
- [ ] Perks inside a row are grouped by cadence, monthly first — a monthly credit is the
      one that recurs most and gets checked most
- [ ] **Empty states carry the next action.** No cards → how to add one. A card with no
      perks → add one. Not a dead end
- [ ] Renaming a card, inline, via `PATCH /accounts/{id}`
- [ ] Reads "available", never "unused" — the framing both reference apps use
- [ ] Tests: multiple cards render as separate rows; a rename calls the API and updates;
      totals come from the API and are not recomputed in the component

## Files
- `web/src/app/(dashboard)/cards/page.tsx`
- `web/src/components/cards/card-row.tsx`
- `web/src/components/cards/card-row.test.tsx`
- `web/src/test/msw.ts`

## Notes

**Owns `page.tsx` and `card-row.tsx` only.** 056–059 each own their own component file so
this wave can run in parallel — see the lane rules in `tickets/README.md`. Whoever takes
this ticket lands the slots as empty placeholders so the others have something to fill.

Money renders from integer cents through the existing formatter. No dividing by 100 in a
component.
