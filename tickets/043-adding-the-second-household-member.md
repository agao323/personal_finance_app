# 043 — Adding the second household member
Status: done
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
- [x] A way to add a household member: email and display name, creating an active
      `users` row
- [x] An **invitation** the new member redeems to register their own passkey against
      their own account — single-use, time-limited, and never granting a session by
      itself
- [x] Redeeming it requires passing Cloudflare Access first, so the invitation is a
      second factor rather than the only one
- [x] Deactivating a member: `is_active = false` revokes them on the next request,
      without deleting the history their ownership stakes refer to
- [x] The Access policy step is documented as the manual one it is, with the
      consequences of forgetting it
- [x] Tests: functional for redeeming an invitation, for an expired one, for a reused
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

## Done — 2026-08-20

Migration 0003 adds `invitations`. **Only the token's SHA-256 is stored** — not a
password hash, because 24 random bytes have no dictionary to attack and nothing for a
work factor to buy. What matters is that a database dump, or any backup, contains no
usable invitation.

**The redemption routes take no `CurrentUser`, deliberately**, and that is the whole
ticket. `/auth/register/*` registers a passkey for whoever is signed in, so an owner
opening an invitation link in their own browser would bind the newcomer's authenticator
to the owner's account — and every ownership figure here is per-user, so nothing on
screen would look wrong. There is a test asserting the challenge is issued against the
invited user's id and not the inviter's.

The contract test caught that exemption before I declared it: two routes with no
authentication, correctly refused until listed as public with the reason. That guard has
now paid for itself twice.

**Every invitation failure returns the same message** — unknown, expired, already
spent. The token is the secret, and distinguishing the cases is a way to probe it.

**No delete, only deactivate.** `ownership_stakes.owner_user_id` is `ON DELETE RESTRICT`
because a stake is a historical fact; removing the user it points at would silently
rewrite past net worth. Deactivating takes effect on the very next request, since
`current_user` reads `is_active` every time. You also cannot deactivate yourself — with
one active member that leaves nobody able to undo it.

`EmailStr` was rejected in favour of a constrained string. It would have added
`email-validator` to check a syntax that is not what matters: the address has to match
the Cloudflare Access policy *exactly*, and no format check can tell you whether it
does. A typo that is still a valid address passes either way.

Two mistakes of mine worth noting. A test asserted a 409 and got a 401, because
inserting a credential shut the bootstrap window and the request lost its identity —
the bootstrap behaving exactly as designed. And a `location` stub without `href` broke
every fetch in a component test, which is the *second* time this session; relative URLs
resolve against `href`, not `origin`.
