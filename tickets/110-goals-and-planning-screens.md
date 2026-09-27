# 110 — Goals and planning screens
Status: todo — order provisional
Wave: 11   Lane: W
Touches: none
Blocked by: 108, 109
Integrates with: 111
Read first: docs/ADVISOR.md#data-model-additions

## Goal
Goals can be set and seen, with their progress; assumptions can be read and changed, with their
history — on a phone, in a short visit.

## Acceptance criteria
- [ ] `/goals`: goals with progress (a bar and the figures, from `GoalRead.progress`; "not yet
      computed" while it is null), add and edit forms per kind. Edit and archive sit **on the goal
      row**.
- [ ] A spending-limit goal links to its category on the Spending screen, and the Spending screen
      shows the limit beside that category's bar.
- [ ] `/settings/planning`, beside the existing `/settings/household`: your birth year and target retirement year; the current
      assumptions with "defaults" shown when they are; editing appends a new version and the
      history is listed beneath.
- [ ] Settled data stays on screen while refetching; saving one goal does not reload the list.
- [ ] "Goals" in the nav after Spending.
- [ ] Tests (MSW): each goal kind's form validation; progress null and present; an assumptions edit
      appends and the history grows by one; the mix must total 100 before saving.

## Files
- `web/src/app/(dashboard)/goals/page.tsx` (new)
- `web/src/components/goals/goal-row.tsx`, `goal-form.tsx` (new)
- `web/src/app/(dashboard)/settings/planning/page.tsx` (new)
- `web/src/components/goals/goal-row.test.tsx`

## Notes
The limit beside the Spending screen's category bar is the part most likely to be seen monthly, and
the reason spending-limit goals lead this wave.
