# 094 — The Insights panel on the dashboard
Status: done
Wave: 9   Lane: W
Touches: none
Blocked by: 081
Integrates with: 093
Read first: docs/ADVISOR.md#findings

## Goal
The dashboard says what needs attention — an expiring credit, a subscription that went up, a
balance four months old, a transfer counted as spending — with the evidence, as-of dates, and a
button that goes where to fix it. No model.

## Acceptance criteria
- [x] A panel on the dashboard below the stat tiles: the top five findings in the server's order,
      with "show all" expanding **in place**.
- [x] Follows the dashboard's Mine / Household toggle.
- [x] Each finding: severity marker, title **rendered as text** (never markdown or HTML), evidence
      figures via `lib/format.ts`, as-of date, a stale badge where evidence is stale.
- [x] **The action sits on the finding it acts on**, not in the panel header. `Screen` values map
      to routes in one function, `lib/screens.ts`, unit-tested for every enum value.
- [x] **Settled findings stay on screen while refetching.** Toggling scope or returning to the
      dashboard never collapses the panel to a loading state once findings have arrived — the
      pattern from ticket 070.
- [x] Empty state: "Nothing needs attention." Error state reuses `states.tsx`.
- [x] Laid out for a phone first.
- [x] Tests (MSW, typed from `api-types.ts`): order preserved; a stale finding shows the
      update-balance action; the scope toggle refetches without clearing; a title containing
      `<img src=x>` renders as literal text; empty and error states.

## Files
- `web/src/components/insights/insights-panel.tsx` (new)
- `web/src/components/insights/finding-row.tsx` (new)
- `web/src/lib/screens.ts` (new)
- `web/src/app/(dashboard)/page.tsx`
- `web/src/components/insights/insights-panel.test.tsx`

## Notes
Built against MSW from the moment 081 lands; it does not wait for 093. Point it at the real
endpoint as soon as 093 merges — semantic mismatches (an empty list where the panel expected a
missing field) are what the mocks cannot catch.

The owner uses this on a phone, in short visits. A panel that flashes to a spinner every time the
toggle moves costs the owner their place, and an action that lives in a header rather than on its
finding is one they will not find.

## Done — 2026-09-27

- The panel sits between the stat tiles and the net worth chart, not keyed on the view, so a
  Mine / Household switch keeps the findings on screen with a "Refreshing" mark until the other
  view's arrive — the test asserts no skeleton appears.
- `lib/screens.ts` is the one screen-to-route mapping, used by finding actions now and by the chat's
  screen tokens in 105. `account` and `cards` take an id where one is given (`/accounts/7`,
  `/cards/4`).
- Severity is a coloured dot **and** a visually hidden label, so it is not carried by colour alone.
- Evidence is formatted with the existing integer-exact formatters; months render from tenths in
  integer arithmetic.
- The existing dashboard tests gained an `/insights` handler, because MSW refuses an unhandled
  request and the panel fetches on mount.
