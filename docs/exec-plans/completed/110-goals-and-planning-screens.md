# 110 — Goals and planning screens
Status: done
Wave: 11   Lane: W
Touches: none
Blocked by: 108, 109
Integrates with: 111
Read first: docs/ADVISOR.md#data-model-additions

## Goal
Goals can be set and seen, with their progress; assumptions can be read and changed, with their
history — on a phone, in a short visit.

## Acceptance criteria
- [x] `/goals`: goals with progress (a bar and the figures, from `GoalRead.progress`; "not yet
      computed" while it is null), add and edit forms per kind. Edit and archive sit **on the goal
      row**.
- [x] A spending-limit goal links to its category on the Spending screen, and the Spending screen
      shows the limit beside that category's bar.
- [x] `/settings/planning`, beside the existing `/settings/household`: your birth year and target retirement year; the current
      assumptions with "defaults" shown when they are; editing appends a new version and the
      history is listed beneath.
- [x] Settled data stays on screen while refetching; saving one goal does not reload the list.
- [x] "Goals" in the nav after Spending.
- [x] Tests (MSW): each goal kind's form validation; progress null and present; an assumptions edit
      appends and the history grows by one; the mix must total 100 before saving.

## Files
- `web/src/app/(dashboard)/goals/page.tsx` (new)
- `web/src/components/goals/goal-row.tsx`, `goal-form.tsx` (new)
- `web/src/app/(dashboard)/settings/planning/page.tsx` (new)
- `web/src/components/goals/goal-row.test.tsx`

## Notes
The limit beside the Spending screen's category bar is the part most likely to be seen monthly, and
the reason spending-limit goals lead this wave.

## Done — 2026-09-28

- `/goals`: each row states its target in one line (`lib/goals.ts`), shows progress as a bar and
  figures once 111 computes it — "Progress not yet computed." until then — and carries Edit and
  Archive (Restore when archived) on the row itself. Adding puts the goal at the top; saving
  or archiving replaces only that row.
- The forms ask each kind for its own fields and say what is missing before anything is sent.
  Months are typed as "6" or "4.5" and sent as tenths; money goes through the shared
  `MoneyInput` as cents. Savings targets offer open, non-liability accounts only.
- The Spending screen reads active spending-limit goals and shows "limit $400" beside the
  category it limits — in the warning colour, and said in the bar's accessible name, when over.
  A goal's link opens the screen with `?category=<id>`: drilled into its parent with it
  selected.
- `/settings/planning`: the profile (years only) and the assumptions in use, marked "Defaults"
  while they are. "Change" opens a form; saving posts a new version on top and moves the old one
  into "Earlier versions". The mix shows a running total and will not save off 100%.
  Percentages convert to and from basis points by string arithmetic, never a float.
- Checked on a phone viewport against this branch's API: the goals list, the Spending screen
  opened from a goal's link with the limit beside Restaurants, and the planning page.
- Like `/settings/household`, `/settings/planning` is reached by its URL; nothing links to either
  from the nav.
