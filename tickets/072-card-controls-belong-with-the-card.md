# 072 — Card controls belong with the card
Status: todo
Wave: 7   Lane: —
Blocked by: none
Read first: none

## Goal
Renaming and deleting a card move out of the list rows and into the top right of the card's
own summary panel, where the fee button already is. The list goes back to being a list.
Editing the fee moves to sit beside the fee figure instead of in the panel header.

## Acceptance criteria
- [ ] The list rows carry no action buttons. Name, institution, available, and the
      running-out count only.
- [ ] "Add a card" stays in the list: it acts on the list, not on any one card.
- [ ] The detail summary header carries rename and delete, in that order, as icon buttons
      with the same tooltips and the same red delete tone they had in the list.
- [ ] Deleting the open card navigates back to `/cards`. Leaving the reader on a detail page
      for a card that no longer exists is what "No such card" would otherwise mean.
- [ ] The fee control sits inside the Annual fee figure, labelled for that figure, not in the
      header.
- [ ] Tests: component — the list renders no buttons other than "Add a card"; the detail
      header renames and deletes; deleting pushes to `/cards`.

## Files
- `web/src/components/cards/card-list.tsx`
- `web/src/components/cards/card-detail.tsx`
- `web/src/components/cards/card-list.test.tsx`, `card-detail.test.tsx`

## Notes
Ticket 066 put these in the list deliberately, so that they would not disappear when a card
was open. That reasoning was wrong in one respect: with a card open, its own panel is where
you are looking, and two icon buttons per row in a narrow column crowds out the name and the
figure the row exists to show.
