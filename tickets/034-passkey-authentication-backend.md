# 034 — Passkey authentication — backend
Status: todo
Wave: 3   Lane: —
Blocked by: 012, 019
Read first: docs/SECURITY.md#auth

## Goal
WebAuthn registration and authentication endpoints with the `users` table as a hard allowlist,
plus session issuance. Replaces the stub `current_user` from 012.

## Acceptance criteria
- [ ] Registration and authentication ceremony endpoints using the `webauthn` library
- [ ] `credentials` rows storing public key and sign count, FK to `users`
- [ ] **RP ID from config** — the registrable parent domain in production, `localhost` in dev
- [ ] Origin validation accepting the web app's origin
- [ ] Allowlist is the `users` table filtered to `is_active` — no separate allowlist config
- [ ] Session cookie: `httpOnly`, `secure`, `sameSite=lax`, host-scoped, sensible expiry
- [ ] Sign-count regression rejected (cloned-authenticator detection)
- [ ] **`current_user` implementation replaced; signature unchanged from 012**
- [ ] Auth dependency protecting every non-public route
- [ ] Tests: unit for the sign-count check and RP ID resolution across environments; functional for registration, login, replay rejection, and a non-allowlisted email

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
