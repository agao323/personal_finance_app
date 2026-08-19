# 034 — Passkey authentication — backend
Status: done
Wave: 3   Lane: —
Blocked by: 012, 019
Read first: docs/SECURITY.md#auth

## Goal
WebAuthn registration and authentication endpoints with the `users` table as a hard allowlist,
plus session issuance. Replaces the stub `current_user` from 012.

## Acceptance criteria
- [x] Registration and authentication ceremony endpoints using the `webauthn` library
- [x] `credentials` rows storing public key and sign count, FK to `users`
- [x] **RP ID from config** — the registrable parent domain in production, `localhost` in dev
- [x] Origin validation accepting the web app's origin
- [x] Allowlist is the `users` table filtered to `is_active` — no separate allowlist config
- [x] Session cookie: `httpOnly`, `secure`, `sameSite=lax`, host-scoped, sensible expiry
- [x] Sign-count regression rejected (cloned-authenticator detection)
- [x] **`current_user` implementation replaced; signature unchanged from 012**
- [x] Auth dependency protecting every non-public route
- [x] Tests: unit for the sign-count check and RP ID resolution across environments; functional for registration, login, replay rejection, and a non-allowlisted email

## Files
- `api/app/routers/auth.py`
- `api/app/services/webauthn.py`
- `api/app/deps.py`
- `api/tests/test_auth.py`

## Notes
No password fallback and no recovery-code path in v1 — Cloudflare Access is the real gate, so a
lost passkey is recovered by re-registering from behind Access. Adding a weaker fallback would
undermine the whole point.

`sameSite=lax` rather than `strict` because the Cloudflare Access redirect returns the user
cross-site; `strict` would drop the cookie on that navigation.

RP ID must be the registrable parent domain, not the app subdomain — getting this wrong produces
passkeys that work locally and fail in production, which is an expensive way to find out.

## Done — 2026-08-18

**Migration 0002 adds `webauthn_challenges`** — the only schema change since the Wave 1
freeze. A challenge has to be spendable exactly once, and a self-contained signed token
handed to the client is replayable until it expires. Rows are deleted on use and swept
opportunistically when the next ceremony starts.

**The bootstrap window.** Registering a passkey needs a session and getting a session
needs a passkey, so something has to open the door once: `current_user` falls back to
the seeded owner *only while the `credentials` table is empty*. The window closes
permanently the moment the first credential is stored, with no action required, and on
the real deployment it sits behind Cloudflare Access the whole time. An expired or
forged cookie does **not** fall through to it — that would turn session expiry into a
silent downgrade to unauthenticated access. Tested.

**Every ceremony failure returns the same message.** Distinguishing "no such user" from
"wrong authenticator" reports whether an address is in the household.

**Sessions are stateless signed cookies**, not a table. The cost is no server-side
revocation; the mitigations are that `is_active` is read on every request (so removing
someone takes effect immediately) and that rotating `SESSION_SECRET` is a global
logout. Cloudflare Access is the real revocation point.

### The frozen-signature guard was asserting the wrong thing

`test_current_user_signature_is_frozen` asserted `current_user`'s parameter list, which
broke the moment the real implementation needed the request to read a cookie. Routes
never call it directly — they depend on `CurrentUser` — so the parameter list was
guarding the plumbing rather than the guarantee.

It is replaced by `test_every_non_public_route_requires_authentication`, which walks
every route and asserts the dependency is present, with an explicit list of the five
public ones. That is also 034's "auth dependency protecting every non-public route"
criterion, checked rather than asserted in prose.

**Worth knowing:** the first version of that walk passed while checking nothing. This
FastAPI version keeps an included router nested in `app.routes` instead of flattening
its routes in, so a non-recursive walk saw two routes — both of them public — and the
test went green. `test_the_route_walk_finds_the_whole_surface` is the tripwire against
that; it currently sees 33 routes, 28 of them authenticated.

### Addendum — 2026-08-19

`session_secret_is_default` existed but nothing read it, which made it a guard in name
only. The lifespan now **refuses to start** when the default secret is in use on an
https origin: a known signing key lets anyone who has read the repo mint a cookie for
any user id, and nothing about the running app would look wrong. Keyed off
`cookie_secure`, so local dev on `http://localhost` is untouched.

Found while checking the deployed state: `pfa-api` has `DATABASE_URL`, `OWNER_EMAIL` and
`OWNER_DISPLAY_NAME` set, and none of `SESSION_SECRET`, `RP_ID` or `WEB_ORIGIN`. A deploy
before this change would have shipped the repo's own key.
