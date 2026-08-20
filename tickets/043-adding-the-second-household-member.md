# 043 — Adding the second household member
Status: todo
Wave: 5   Lane: —
Blocked by: 041
Read first: docs/ARCHITECTURE.md#users-and-ownership

## Goal
A documented, tested path for a partner to get access — rather than a SQL insert and a
hope.

## Why this is a ticket

`docs/ARCHITECTURE.md` describes the process as: "insert it, add the identity to the
Cloudflare Access policy, register a passkey." That is accurate and it is three systems
deep, with a failure mode at each step and no way to tell which one went wrong:

1. **A `users` row** — currently a hand-written `INSERT`. Get `is_active` wrong and
   `current_user` refuses them with the same message a stranger gets.
2. **The Access policy** — a dashboard edit. Miss it and they never reach the origin.
3. **Their passkey** — and here is the real problem. The bootstrap window is *closed*,
   so they cannot register through `/login`. `/auth/register/options` registers a
   passkey **for whoever is signed in**, so with the owner's session it would attach
   the partner's authenticator to the *owner's* account — silently wrong in the way
   that matters most, since every ownership figure is per-user.

Step 3 is not a UX gap. There is currently **no correct way** for a second person to
get a passkey.

## Acceptance criteria
- [ ] A way to add a household member: email and display name, creating an active
      `users` row
- [ ] An **invitation** the new member redeems to register their own passkey against
      their own account — single-use, time-limited, and never granting a session by
      itself
- [ ] Redeeming it requires passing Cloudflare Access first, so the invitation is a
      second factor rather than the only one
- [ ] Deactivating a member: `is_active = false` revokes them on the next request,
      without deleting the history their ownership stakes refer to
- [ ] The Access policy step is documented as the manual one it is, with the
      consequences of forgetting it
- [ ] Tests: functional for redeeming an invitation, for an expired one, for a reused
      one, and asserting a redeemed invitation attaches the credential to the invited
      user and never to the inviter

## Files
- `api/app/routers/users.py`
- `api/app/models/user.py`
- `web/src/app/(dashboard)/settings/household/page.tsx`
- `api/tests/test_invitations.py`

## Contract change

New endpoints and a migration for an `invitations` table. Both additive.

## Notes

**Do not reopen the bootstrap window.** It is `credentials`-is-empty and it closes
permanently; making it "empty *for this user*" would mean anyone who reached the origin
could claim any account that had not registered yet. The invitation exists precisely so
the window stays shut.

**Deactivate, never delete.** `ownership_stakes.owner_user_id` is `ON DELETE RESTRICT`,
and deliberately: a stake is a historical fact and deleting the user it refers to would
silently rewrite past net worth. Ticket 010 made that choice; this ticket inherits it.

This is scoped as one household of two. Nothing here needs roles, permissions, or
invitation management screens — see the "prefer boring" rule in CLAUDE.md.
