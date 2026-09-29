# Household members

One household, two people at most, ever. The second person is a data-model requirement —
stakes belong to a person, and net worth is computed per viewer — not a product surface.
There are no invitations, roles or permissions.

## What you can do

- **See who is in the household** and who you are signed in as (`/settings/household`, and
  the account menu).
- **Add a member**: an email and a display name, creating an active `users` row. Then add
  the same email to the Cloudflare Access policy — **a manual step in the Cloudflare
  dashboard**, and the screen says so. Miss it and they never reach the app, which from their
  side looks exactly like being refused.
- **Deactivate or reactivate a member.** Takes effect on their very next request.
- **Sign out** from the account menu. The only session is Cloudflare's, so this is a plain
  link to `/cdn-cgi/access/logout`, not an app route.

## Rules and edge cases

- **Cloudflare Access authenticates; the `users` table authorises.** Passing Access is
  necessary and not sufficient: an identity Access admits but the household never added is
  refused ([SECURITY.md](../SECURITY.md#auth)). The API verifies the Access JWT itself —
  signature, issuer, audience — and never trusts a header the web tier attached.
- **Deactivate, never delete.** Stakes reference users with `ON DELETE RESTRICT`: a stake is
  a historical fact, and deleting its owner would rewrite past net worth.
- **You cannot deactivate yourself** — with one active member, nobody would be left to undo
  it (409). **An email already in the household is refused** (409).
- The email must match the Access policy **exactly**; no format check can tell you whether
  it does, so there is none beyond a constrained string.
- **A stuck Access session has a way out**: when an assertion fails, the origin clears
  `CF_Authorization` itself (042). Access's own logout fails precisely when the organisation
  in the cookie no longer resolves — a renamed team — which is when it is most needed. That
  fallback must not be removed.
- Locally there is no Access: `DEV_IDENTITY_EMAIL` names who you are, and is ignored on any
  https origin. The demo serves a fixed synthetic identity.

## Endpoints

| Method | Path | Notes |
|---|---|---|
| GET | `/auth/session` | Who the request is from |
| GET POST | `/members` | List; add (email, display name) |
| PATCH | `/members/{member_id}` | Rename, deactivate, reactivate |

**The `/members` routes have no backend functional tests** since 047b removed the file that
covered them — TD-002.

## Screens and code

`web/src/app/(dashboard)/settings/household/page.tsx`, `components/account-menu.tsx`,
`web/src/proxy.ts`, `web/src/lib/access.ts`. API: `routers/users.py`, `routers/auth.py`,
`deps.py` (`current_user`), `services/access.py`, `models/user.py`.

## Built by

041 (account menu, sign out), 042 (recover from a rejected Access session), 043 (adding the
second member — then with invitations and passkeys), 044 (recovery from behind Access), 047a
(Access becomes the authentication), 047b (the passkey layer and invitations removed).
Decision record: [ADR 0007](../adr/0007-drop-passkeys.md).
