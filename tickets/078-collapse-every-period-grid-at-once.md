# 078 — Collapse every period grid at once
Status: done
Wave: 7   Lane: —
Blocked by: none
Read first: none

## Goal
One control opens or closes every credit's period grid on a card, instead of clicking each
one shut in turn.

## Acceptance criteria
- [ ] The Credits section header carries one toggle: it opens every grid when none is open,
      and closes all of them when any is.
- [ ] Its label says which it will do.
- [ ] Opening and closing individual grids still works and keeps the toggle honest.
- [ ] The toggle is absent when the card has no credits to show.
- [ ] Tests: component — opening one grid then using the toggle closes it; the toggle opens
      all grids when none is open; the label changes with the state.

## Files
- `web/src/components/cards/card-detail.tsx`
- `web/src/components/cards/card-detail.test.tsx`

## Notes
Which grids are open moves out of each row and into the card, because "are any open" is a
question no single row can answer. It is view state and deliberately not persisted: a card
that reopens with six grids expanded is worse than one that reopens closed.
