# 104 — The `/advisor` screen: conversations, scope, and whether it is on
Status: todo
Wave: 10   Lane: W
Touches: none
Blocked by: 081
Integrates with: 097, 099
Read first: docs/ADVISOR.md#scope, docs/ADVISOR.md#cost

## Goal
There is somewhere to ask: a screen listing your conversations, a way to start one as Mine or
Household, and an honest statement of whether the advisor is available and, if not, why.

## Acceptance criteria
- [ ] "Advisor" in the nav, between Cards and Import.
- [ ] `/advisor` lists the current user's conversations, newest first, and starts a new one with the
      dashboard's Mine / Household toggle (reuse `view-toggle.tsx`).
- [ ] A status line from `/advisor/status`: available; switched off; the monthly cap reached, with
      the date it resets; the demo. The question box is disabled whenever the advisor is not
      available, and the Insights panel is linked as the thing that still works.
- [ ] **Delete sits on the conversation it deletes**, not in a toolbar. Its confirmation says the
      conversation is gone from the app now and remains in any backup file already written.
- [ ] Question input: 2,000 characters, with the count shown near the limit.
- [ ] Settled lists stay on screen while refetching; deleting one conversation does not reload the
      others.
- [ ] Laid out for a phone first.
- [ ] Tests (MSW): list and create in both scopes; each status reason renders its message and
      disables input; delete removes one row in place; the nav item is active on `/advisor`.

## Files
- `web/src/app/(dashboard)/advisor/page.tsx` (new)
- `web/src/components/advisor/conversation-list.tsx` (new)
- `web/src/components/advisor/status-line.tsx` (new)
- `web/src/components/nav.tsx`
- `web/src/components/advisor/conversation-list.test.tsx`
