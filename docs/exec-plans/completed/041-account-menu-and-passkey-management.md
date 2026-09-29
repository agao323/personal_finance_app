# 041 — Account menu: identity, sign out, and passkey management
Status: done
Wave: 5   Lane: —
Blocked by: 035
Read first: docs/SECURITY.md#auth

## Goal
Somewhere in the app that says who you are, lets you sign out, and lets you add or
remove a passkey. All three exist as capabilities and none has a UI.

## Why now

Three things are true today and none of them is obvious:

- **`GET /auth/session` is never called by the web app.** Nothing on screen says whose
  numbers these are. With one user that reads as minimalism; the moment a partner is
  added it is a bug.
- **`POST /auth/logout` exists and nothing calls it.** There is no way to sign out
  except by clearing cookies, which is what made a stale session take hours to recover
  from.
- **A signed-in user can already register another passkey** — `/auth/register/options`
  takes `CurrentUser`, so it works with a session, not only during the bootstrap. But
  the only button that calls it lives on `/login` and is captioned as a first-time
  action. **In practice there is no way to add a second device**, which means a new
  laptop or a lost phone is currently an incident rather than a task.

That last one is the reason this is not cosmetic.

## Acceptance criteria
- [x] Account control in the nav showing the signed-in user's display name, from
      `GET /auth/session`
- [x] **Sign out**, clearing the application session
- [x] **Sign out of Cloudflare Access too**, as a separate and clearly-labelled action —
      see the open question below
- [x] A **passkeys** view: list registered credentials with their created and last-used
      dates, add one for this device, remove one
- [x] **Removing the last passkey is refused**, with a message saying why. An account
      with no credential can only be recovered through the bootstrap window, which is
      closed the moment any credential exists — so removing the last one is a lockout,
      not a sign-out
- [x] Removing a credential that is not the one you are currently using is allowed, and
      the current one is marked so you can tell them apart
- [x] Tests: component tests for the menu, the sign-out call, the add-device ceremony
      against a stubbed authenticator, and the refuse-to-remove-the-last-one path

## Files
- `web/src/components/account-menu.tsx`
- `web/src/app/(dashboard)/settings/passkeys/page.tsx`
- `api/app/routers/auth.py`
- `api/app/schemas/auth.py`

## Contract change

Needs a re-freeze — two additive endpoints:

| Method | Path | Returns |
|---|---|---|
| GET | `/auth/credentials` | id, created_at, last_used_at, whether it is the current session's |
| DELETE | `/auth/credentials/{id}` | 204, or 409 when it is the last one |

Neither returns the public key or the credential id bytes. A list of "which devices can
sign in as me" is enough for the screen and is not itself a secret; the key material is,
and there is no reason for it to leave the database.

## Open question — what should "Sign out" do?

Two sessions exist and they expire independently: the application's passkey session
(14 days) and Cloudflare Access's (whatever the application's Session Duration is).

- **App only.** Fast, and the common case is "lock this app". You are still through
  Access, so signing back in is one passkey prompt.
- **Both.** Correct on a shared or borrowed machine, but signing back in costs a full
  Access round trip.

**Recommendation: both actions, with app-only as the primary.** A single button that
did both would make the frequent case expensive; a single button that did only the app
would leave a "signed out" state where Access still lets you through, which is exactly
the kind of half-truth this project avoids elsewhere.

## Notes

The bootstrap path in `deps.current_user` is unchanged by this ticket and must stay
that way — it is what opens the door once, and it closes permanently on the first
credential.

The `/login` page's "Register a passkey" button should be re-captioned once this lands:
it is genuinely the first-run action there, and the add-a-device action lives here.

## Done — 2026-08-20

Took the recommendation on the open question: **two sign-out actions**, app-only as the
primary and "Sign out of Access too" beneath it for a shared machine.

**The session cookie now carries the credential id** that issued it, so the list can
mark the device you are holding. Cookies minted before this field exists stay valid and
simply cannot mark one — nobody is signed out by a deploy that added a field, and there
is a test for that.

`current_identity` is a **separate dependency** from `current_user`. Only this screen
needs to know *which* passkey signed you in, and `current_user`'s behaviour is relied on
by every route in the app — the contract test asserts exactly that. Widening it to carry
more would have put the whole surface at risk for one screen's benefit.

**Removing the last passkey is refused twice**: the API answers 409, and the button is
disabled before you get there. Two guards rather than one because there is no undo — the
bootstrap window shuts permanently on the first credential, so an account with none
cannot be recovered from inside the app at all. The screen shows the API's own message
rather than a local copy that could drift from the rule.

A removal request for somebody else's credential gets the same 404 a nonexistent id
does. Whether a given id belongs to another user is not a question this endpoint should
answer.

The `/login` copy was left alone. It already reads as the first-run action it is, and
linking to a signed-in settings page from a signed-out screen would help nobody.
