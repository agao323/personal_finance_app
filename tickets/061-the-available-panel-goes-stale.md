# 061 — Marking a credit used does not refresh what is available
Status: done
Wave: 7   Lane: —
Blocked by: none

## The bug
Mark a credit used from inside a card row and the "Available to use" panel at the top keeps
showing it. The figure and the list are both wrong until a reload.

**Cause.** `UpcomingPanel` fetches on its own `revision`, which only its own MarkButton
bumps. A mark from a card row calls the page's `reload`, which refetches `/cards` — the
panel never hears about it.

## Acceptance criteria
- [x] One refresh signal for the screen. A change anywhere refetches everything that could
      have changed, because "which panels does this affect" is a question the caller should
      not have to answer correctly every time
- [x] The panel keeps its own horizon state — that is a view preference, not shared data
- [x] Tests: marking from a card row refetches `/perks/upcoming`; marking from the panel
      still refetches `/cards`

## Files
- `web/src/app/(dashboard)/cards/page.tsx`
- `web/src/components/cards/upcoming.tsx`

## Done — 2026-09-26

The panel takes the screen's `revision` as a prop rather than keeping its own counter. One
signal: a change anywhere refetches everything that could have changed, because "which
panels does this affect" is a question every caller would have to answer correctly, and one
of them would eventually not.

Mutation-tested. Dropping `revision` from the effect's dependencies makes the page test
fail, so the regression guard is real rather than incidental.
