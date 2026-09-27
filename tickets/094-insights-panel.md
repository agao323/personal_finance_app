# 094 — The Insights panel on the dashboard
Status: todo
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
- [ ] A panel on the dashboard below the stat tiles: the top five findings in the server's order,
      with "show all" expanding **in place**.
- [ ] Follows the dashboard's Mine / Household toggle.
- [ ] Each finding: severity marker, title **rendered as text** (never markdown or HTML), evidence
      figures via `lib/format.ts`, as-of date, a stale badge where evidence is stale.
- [ ] **The action sits on the finding it acts on**, not in the panel header. `Screen` values map
      to routes in one function, `lib/screens.ts`, unit-tested for every enum value.
- [ ] **Settled findings stay on screen while refetching.** Toggling scope or returning to the
      dashboard never collapses the panel to a loading state once findings have arrived — the
      pattern from ticket 070.
- [ ] Empty state: "Nothing needs attention." Error state reuses `states.tsx`.
- [ ] Laid out for a phone first.
- [ ] Tests (MSW, typed from `api-types.ts`): order preserved; a stale finding shows the
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
toggle moves costs him his place, and an action that lives in a header rather than on its finding
is one he will not find.
