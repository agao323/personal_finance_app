# 046 — Signed-out pages render the signed-in app's chrome
Status: closed — superseded by 047b
Wave: 5   Lane: —
Blocked by: none
Read first: docs/ARCHITECTURE.md#request-path

> **Do not implement.** Superseded by [ADR 0007](../docs/adr/0007-drop-passkeys.md):
> the passkey layer is being removed and `/login` ceases to exist, so this defect is
> deleted rather than fixed. Ticket 047b closes it. Kept in the tree because what a
> removed subsystem was costing is worth being able to read later.

## Goal
`/login`, `/recover`, and `/invitation` show only what they need. No nav to pages you
cannot open, no account menu for an account you are not in, and no announcement that a
session ended when you never had one.

## The bug

On `/login`, a bar appears at the top of every page load:

> Your session ended. Anything on screen may be out of date.  **[Sign in again]**

Both sentences are false. No session ended — there wasn't one. Nothing on screen is out
of date — there is nothing on screen, because you are signed out. And "Sign in again" is
a button to the page you are already on.

It is not a race or a stale cache. It is deterministic, on every load, on every device:

1. `layout.tsx` is the **root** layout, so `Nav` and `SessionExpiry` render on every
   route — including the three that exist precisely for people with no session.
2. `Nav` renders `AccountMenu`.
3. `AccountMenu` fetches `GET /auth/session` on mount, unconditionally.
4. Signed out, that is a 401 — the correct answer.
5. `apiFetch` dispatches `SESSION_EXPIRED_EVENT` on **any** 401, whether or not a session
   ever existed.
6. `SessionExpiry` listens and shows the bar.

So the app asks a question only a signed-in reader can answer, on a page for readers who
are not, and reports the expected answer as a failure.

`SessionExpiry`'s own header says a 401 mid-session "is not an error to render in a
panel — nothing is broken, the session simply ended." That reasoning is sound and holds
only **mid-session**. Nothing enforced the precondition.

## The same root cause, unreported

The full nav — Dashboard, Spending, Accounts, Transactions, Import, Rules — also renders
on `/login`. Every link bounces off `proxy.ts` back to `/login`. There is a
`(dashboard)` route group already and it has **no layout of its own**; all the chrome
sits in the root layout instead.

## Acceptance criteria
- [ ] Move `Nav` and `SessionExpiry` into a new `(dashboard)/layout.tsx`. The root layout
      keeps `<html>`, `<body>`, fonts, metadata, and `DemoBanner`
- [ ] `/login`, `/recover`, and `/invitation` render no nav, no account menu, and no
      session bar
- [ ] The expiry bar still appears for a genuine mid-session 401 on a dashboard page —
      that behaviour is correct and is the reason the component exists
- [ ] `AccountMenu` no longer treats its own 401 as an expiry. It is the one caller that
      **asks whether there is a session**; a 401 is a valid answer to that question, not
      the failure of an assumption. Every other caller assumes one and is right to raise
- [ ] Tests: the three signed-out pages render no nav and no bar; a 401 from a data
      endpoint still raises it; a 401 from `/auth/session` alone does not

## Files
- `web/src/app/layout.tsx`
- `web/src/app/(dashboard)/layout.tsx`
- `web/src/components/account-menu.tsx`
- `web/src/app/login/page.test.tsx`

## Notes

**Both halves are needed.** Moving the layout alone leaves `AccountMenu` able to raise a
false expiry anywhere it renders. Fixing the 401 alone leaves a nav full of dead links on
the sign-in page. They are one cause with two symptoms.

**Do not suppress the bar by checking the pathname.** `SessionExpiry` would then know
about routing, which is exactly what `api.ts` dispatches an event to avoid. Layout
placement is the mechanism the App Router already provides.

Related to [045] — same screen, same shape of error: a correct refusal reported as
something it is not.

## Closed — 2026-08-20

Deleted rather than fixed, by 047b. There are no signed-out pages left. `/login`, `/recover` and `/invitation` were the
three, and all three were deleted; `SessionExpiry` went with them, so nothing can
announce a session that never existed. The `(dashboard)` layout split this ticket
asked for turned out to be unnecessary — not because the reasoning was wrong, but
because the pages it was separating stopped existing.
