# 070 — Refresh without flashing
Status: todo
Wave: 7   Lane: —
Blocked by: none
Read first: docs/ARCHITECTURE.md#the-api-contract

## Goal
Marking a credit, or switching a window, updates the numbers in place. Today every one of
those replaces the whole screen with skeletons and rebuilds it, which reads as a page reload
for a one-field change.

## Acceptance criteria
- [ ] The cards layout keeps the last loaded wallet on screen while a refresh is in flight.
      A skeleton appears only when there is nothing to show yet.
- [ ] A refresh that fails keeps the data already on screen and surfaces the failure beside
      it. The full-panel `ErrorState` is for a first load that failed.
- [ ] `UpcomingPanel` and `HistoryPanel` do the same: existing figures stay, marked as
      refreshing, rather than being replaced by skeletons.
- [ ] A `Refreshing` indicator in `components/states.tsx` — one implementation, used by all
      three.
- [ ] Nothing unmounts on refresh: no layout shift, and an open form stays open.
- [ ] Tests: component — after a mark, the previous totals are still in the document while
      the refetch is in flight, and no `status`/`Loading` placeholder replaces them; a failed
      refresh keeps the stale figures and shows the error.

## Files
- `web/src/app/(dashboard)/cards/layout.tsx`
- `web/src/components/cards/upcoming.tsx`
- `web/src/components/cards/history.tsx`
- `web/src/components/states.tsx`
- `web/src/app/(dashboard)/cards/page.test.tsx`

## Notes
Keep the settled-state cell pattern. The change is what the derived values mean: `pending`
becomes "nothing has ever arrived" rather than "the response in hand is for an older key",
and the data falls back to the last good response instead of null.

The card detail page keys off the same `pending`, so this fixes the detail column too — it
currently returns a skeleton for the whole card on every mark.
