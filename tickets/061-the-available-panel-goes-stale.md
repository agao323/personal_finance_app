# 061 — Marking a credit used does not refresh what is available
Status: todo
Wave: 7   Lane: —
Blocked by: none

## The bug
Mark a credit used from inside a card row and the "Available to use" panel at the top keeps
showing it. The figure and the list are both wrong until a reload.

**Cause.** `UpcomingPanel` fetches on its own `revision`, which only its own MarkButton
bumps. A mark from a card row calls the page's `reload`, which refetches `/cards` — the
panel never hears about it.

## Acceptance criteria
- [ ] One refresh signal for the screen. A change anywhere refetches everything that could
      have changed, because "which panels does this affect" is a question the caller should
      not have to answer correctly every time
- [ ] The panel keeps its own horizon state — that is a view preference, not shared data
- [ ] Tests: marking from a card row refetches `/perks/upcoming`; marking from the panel
      still refetches `/cards`

## Files
- `web/src/app/(dashboard)/cards/page.tsx`
- `web/src/components/cards/upcoming.tsx`
