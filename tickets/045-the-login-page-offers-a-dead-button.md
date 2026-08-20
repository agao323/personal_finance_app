# 045 — The login page offers a button that cannot work
Status: closed — superseded by 047b
Wave: 5   Lane: —
Blocked by: none
Read first: docs/SECURITY.md#auth

> **Do not implement.** Superseded by [ADR 0007](../docs/adr/0007-drop-passkeys.md):
> the passkey layer is being removed and `/login` ceases to exist, so this defect is
> deleted rather than fixed. Ticket 047b closes it. Kept in the tree because what a
> removed subsystem was costing is worth being able to read later.

## Goal
A second device landing on `/login` is pointed at an action that works, instead of one
that is guaranteed to fail with a message that explains nothing.

## The incident this comes from

2026-08-20, signing in on a phone for the first time. `/login` presents two buttons of
equal weight. The reader tapped **"Register a passkey"** — the reasonable reading of
"this device has no passkey yet" — and got:

```
API 401: Not signed in
```

That refusal is **correct**. The bootstrap window is `credentials`-is-empty and it shut
permanently when the laptop registered. But every part of how it surfaces is wrong:

- The button is **permanently dead for every device after the first**, and still rendered
  at full prominence with encouraging copy beneath it.
- `Not signed in` is the literal `detail` from `deps.current_user`, correct for the
  forty other routes that raise it and meaningless here — on a *sign-in* page, "not
  signed in" is a tautology, not a diagnosis.
- The working paths were both on screen and neither was where the eye went: "Sign in
  with a passkey" above it (correct when the passkey synced), and the `/recover` link
  below (correct when it did not).

Ticket 041 said "The `/login` copy was left alone. It already reads as the first-run
action it is." That judgement was wrong in a way only a second device reveals: the copy
describes the rule accurately and still points the reader at the one button that
cannot succeed.

## Acceptance criteria
- [ ] A 401 from `/auth/register/options` on `/login` produces a message naming both real
      options — sign in with a synced passkey, or register a replacement via `/recover`
- [ ] Never render `Not signed in` to a reader on the sign-in page
- [ ] Consider hiding or demoting the register button once a credential exists, without
      leaking whether the account has one to an unauthenticated caller — an
      unauthenticated probe that distinguishes "this household has registered" from
      "it has not" is a fact worth not answering. If that cannot be done without
      leaking, keep the button and fix only the message
- [ ] Tests: the 401-from-register path renders the guidance and not the raw detail

## Files
- `web/src/app/login/page.tsx`
- `web/src/app/login/page.test.tsx`

## Notes

**Do not reopen the bootstrap window** and do not make it per-user — 043 explains why
that hands any account to whoever reaches the origin first. The button's *behaviour* is
right; only its prominence and its failure message are wrong.

**The generic-`detail` problem is probably not unique to this screen.** `apiFetch`
renders `API <status>: <detail>` for every failure, and `detail` is written for whichever
route raises it. Worth a sweep, but not in this ticket — add another if the sweep finds
more.

## Closed — 2026-08-20

Deleted rather than fixed, by 047b. The dead button, the page it sat on, and the 401 it produced are all gone.
