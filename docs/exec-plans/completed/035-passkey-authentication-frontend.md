# 035 — Passkey authentication — frontend
Status: done
Wave: 3   Lane: —
Blocked by: 034, 025
Read first: docs/SECURITY.md#auth

## Goal
Sign-in and passkey registration UI, session handling, and route protection.

## Acceptance criteria
- [x] Sign-in page invoking the WebAuthn browser API
- [x] Passkey registration flow
- [x] Middleware redirecting unauthenticated users
- [x] Session expiry surfaced as a re-authentication prompt, not a raw 401 or an opaque failure
- [x] **The demo build omits auth entirely at build time**
- [x] Tests: component tests for the sign-in flow against a mocked credentials API, the registration flow, and the expiry path

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

## Done — 2026-08-18

**`middleware.ts` is now `proxy.ts`.** Next 16 deprecated the `middleware` file
convention and renamed it; the dev server says so on every boot. Unfortunate naming
overlap with the thing this repo already calls "the proxy" — the `/api/[...path]`
route handler — so the file says which is which.

**`/api/*` is exempt from the redirect**, not just `/api/auth/*`. Redirecting a `fetch`
answers it with a 200 and an HTML body, which the caller parses as JSON and reports as
a mystery. An expired session has to come back as a real 401 so the app can say what
happened — which is the thing the ticket notes the BFF topology buys, and redirecting
it away would waste it. The 401 is announced as an event from `apiFetch` and the layout
renders a bar offering to sign in again; a redirect from inside `apiFetch` would
discard whatever the reader was partway through.

**The redirect is a convenience, not the boundary.** The proxy can only check that a
cookie is *present* — verifying the signature needs the secret, and a second copy of it
in the edge runtime is the one thing that must not leak. Every request is authenticated
again by the API.

Two bugs the tests caught, both real:

- `startsWith("/login")` made `/loginsomething` public. Now an exact match or a
  separator-terminated prefix.
- `next.startsWith("/")` let `//evil.example` through — a protocol-relative URL, not a
  path. An open redirect on a sign-in page is how a phishing link borrows your domain.

**The demo bypass is build-time**: `NEXT_PUBLIC_DEMO` is inlined and the dead branch is
dropped, so the demo bundle does not contain the sign-in path rather than merely
declining to use it.

The ceremonies themselves are tested against a stubbed `navigator.credentials`. A real
authenticator is 038's Playwright run — jsdom has no WebAuthn, and pretending otherwise
would be a test that asserts my own mock.
