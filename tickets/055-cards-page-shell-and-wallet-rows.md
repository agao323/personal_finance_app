# 055 — Cards page: the shell and one row per card
Status: done
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
- [x] `/cards` composes: the upcoming panel (056), then one row per card, then history
      (058). This ticket owns the composition and the row; the panels are slots
- [x] A card row shows name, institution, perk count, **available value this period**, and
      a closed badge where relevant. Expanding reveals its perks
- [x] Perks inside a row are grouped by cadence, monthly first — a monthly credit is the
      one that recurs most and gets checked most
- [x] **Empty states carry the next action.** No cards → how to add one. A card with no
      perks → add one. Not a dead end
- [x] Renaming a card, inline, via `PATCH /accounts/{id}`
- [x] Reads "available", never "unused" — the framing both reference apps use
- [x] Tests: multiple cards render as separate rows; a rename calls the API and updates;
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

## Done — 2026-09-26

The row shows a card's whole state before you expand it — available value and credit count
sit in the header, so collapsing keeps the summary. A test asserts that, because the point
of the row is a six-card wallet you can scan without opening anything.

**Adding a card deliberately links to `/accounts/new`** rather than creating one here. A
card *is* an account; a second way to create that row would be a second source of truth for
it, and the account form already handles the ownership stake a new account needs.

Retired credits are shown in their own group rather than hidden. A retired credit you
cannot see is one you will add again by mistake.
