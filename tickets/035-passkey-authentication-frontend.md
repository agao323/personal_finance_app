# 035 — Passkey authentication — frontend
Status: todo
Wave: 3   Lane: —
Blocked by: 034, 025
Read first: docs/SECURITY.md#auth

## Goal
Sign-in and passkey registration UI, session handling, and route protection.

## Acceptance criteria
- [ ] Sign-in page invoking the WebAuthn browser API
- [ ] Passkey registration flow
- [ ] Middleware redirecting unauthenticated users
- [ ] Session expiry surfaced as a re-authentication prompt, not a raw 401 or an opaque failure
- [ ] **The demo build omits auth entirely at build time**
- [ ] Tests: component tests for the sign-in flow against a mocked credentials API, the registration flow, and the expiry path

## Files
- `web/src/app/login/page.tsx`
- `web/src/lib/webauthn.ts`
- `web/src/middleware.ts`

## Notes
The demo bypass is **build-time, not runtime** — the demo bundle must not contain a code path
capable of authenticating against the real API.

Session expiry surfacing cleanly is a real requirement here rather than a nicety: because the
browser talks only to the Next.js origin, an expired session comes back as a proper 401 through
the proxy. That's one of the things the BFF topology buys — handle it properly rather than
letting it become a mystery reload.
