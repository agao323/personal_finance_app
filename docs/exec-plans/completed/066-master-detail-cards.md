# 066 — Cards as master–detail, one card at a time
Status: done
Wave: 7   Lane: —
Blocked by: none
Read first: docs/exec-plans/completed/055-cards-page-shell-and-wallet-rows.md

## Goal
A card list on the left, one card's detail on the right, each card at its own URL.

## Why this and not the credits table

I proposed a single cross-card credits table and was wrong about the task. The actual
habit is **pick a card, then look at it** — not scan every credit across the wallet. A
table optimised for comparing credits across cards would put a step in front of the
common case to serve a rare one.

Stacked collapsible cards had to go regardless: every card added a section, so the page
grew without bound and the thing you wanted was nested a level too deep. Master–detail
fixes that without inverting the hierarchy the way a flat table would.

## Acceptance criteria
- [x] `/cards` — the list, plus the cross-card "available to use" panel as an overview.
      Nothing selected
- [x] `/cards/[id]` — the same list, with that card's detail beside it. **A real URL**, so
      a card can be bookmarked and the back button works
- [x] The list is one compact row per card: name, institution, available value, and a mark
      when something on it is running out. Ten cards is ten lines
- [x] The detail opens with the compact summary — credits, available, annual fee, realised
      — then the credits themselves, then that card's history
- [x] **Responsive without a second layout.** Below the breakpoint, the list and the detail
      are separate screens: `/cards` shows the list full width, `/cards/[id]` shows the
      detail full width with a back link. Above it, both are visible. One component tree,
      CSS decides
- [x] History is scoped to the selected card — `/cards/history` gains an optional
      `account_id`. Filtering the whole wallet's history in the browser would work today
      and grow without bound
- [x] A card that does not exist says so rather than rendering an empty shell
- [x] Tests: the list renders and marks the selected card; the detail loads a card by id;
      an unknown id is handled; history requests carry the account filter

## Files
- `api/app/routers/cards.py`
- `web/src/app/(dashboard)/cards/layout.tsx`
- `web/src/app/(dashboard)/cards/page.tsx`
- `web/src/app/(dashboard)/cards/[id]/page.tsx`
- `web/src/components/cards/card-list.tsx`, `card-detail.tsx`

## Notes

**Navigation, not filtering.** Each card gets a URL, which is what makes the back button
and a bookmark work. Filtering would have been fewer moving parts and no addressable state.

The cross-card credits table is **not** being built. Recorded as a possible later feature
for when the wallet is large enough that looking card-by-card stops being practical.

## Done — 2026-09-26

Card list left, detail right, each card at `/cards/[id]`. The list lives in the layout so
navigating between cards does not refetch the wallet.

`/cards/history` gained `account_id` rather than filtering in the browser: the client-side
version would work today and grow without bound, and `missed_periods` could not be filtered
that way at all — it is counted by walking each perk's periods, not derived from the rows
returned.

Mobile is written but **not verified** — the reader was not looking at it and said so.
