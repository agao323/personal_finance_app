# 074 — Period chips of unequal height
Status: done
Wave: 7   Lane: —
Blocked by: none
Read first: none

## Goal
Every chip in a period grid is the same height, whatever it has to say.

## Acceptance criteria
- [ ] All chips are one uniform height. A chip's second line is always present; its content
      is the recorded partial amount, or `now` for the current period, or nothing.
- [ ] The current period stays identifiable: its ring, its position as the last chip, and
      `current period` in its accessible name.
- [ ] Tests: component — the current chip and an ordinary one render the same number of
      lines; the accessible name says which period is current.

## Files
- `web/src/components/cards/period-grid.tsx`
- `web/src/components/cards/period-grid.test.tsx`

## Notes
The second line was conditional, so a row containing the current period — or a partial
amount — grew taller than the rows around it, and the grid stepped. A calendar is the mental
model here and calendar cells are uniform boxes with mostly-empty space in them.

Reserving the line rather than moving the text inline: at three columns on a phone,
`Sep 2026 now` and a chip carrying an amount both overflow their width, and a chip that
truncates its own marker is worse than one with a blank line under it.
