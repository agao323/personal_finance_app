# 104 — The `/advisor` screen: conversations, scope, and whether it is on
Status: done
Wave: 10   Lane: W
Touches: none
Blocked by: 081
Integrates with: 097, 099
Read first: docs/ADVISOR.md#scope, docs/ADVISOR.md#cost

## Goal
There is somewhere to ask: a screen listing your conversations, a way to start one as Mine or
Household, and an honest statement of whether the advisor is available and, if not, why.

## Acceptance criteria
- [x] "Advisor" in the nav, between Cards and Import.
- [x] `/advisor` lists the current user's conversations, newest first, and starts a new one with the
      dashboard's Mine / Household toggle (reuse `view-toggle.tsx`).
- [x] A status line from `/advisor/status`: available; switched off; the monthly cap reached, with
      the date it resets; the demo. The question box is disabled whenever the advisor is not
      available, and the Insights panel is linked as the thing that still works.
- [x] **Delete sits on the conversation it deletes**, not in a toolbar. Its confirmation says the
      conversation is gone from the app now and remains in any backup file already written.
- [x] Question input: 2,000 characters, with the count shown near the limit.
- [x] Settled lists stay on screen while refetching; deleting one conversation does not reload the
      others.
- [x] Laid out for a phone first.
- [x] Tests (MSW): list and create in both scopes; each status reason renders its message and
      disables input; delete removes one row in place; the nav item is active on `/advisor`.

## Files
- `web/src/app/(dashboard)/advisor/page.tsx` (new)
- `web/src/components/advisor/conversation-list.tsx` (new)
- `web/src/components/advisor/status-line.tsx` (new)
- `web/src/components/nav.tsx`
- `web/src/components/advisor/conversation-list.test.tsx`

## Done — 2026-09-28

- Asking from `/advisor` creates the conversation in the toggle's view and opens
  `/advisor/{id}`. **The question travels in sessionStorage, never the URL** (`lib/advisor.ts`):
  a question can name an amount or a merchant, and a URL lives in history and proxy logs. 105's
  conversation screen takes it once and clears it.
- `REASONS` in `lib/advisor.ts` is the one place every `AdvisorErrorCode` becomes words; 105's
  error events use it too.
- `QuestionBox` is its own component because 105 reuses it for follow-up questions.
- Delete confirms inside its own row ("Keep it" cancels) and removes only that row.
- Laid out single-column, `max-w-2xl`; checked on a phone viewport with 105.
