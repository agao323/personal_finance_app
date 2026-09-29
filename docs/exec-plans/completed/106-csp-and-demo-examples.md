# 106 — A content security policy, and the demo's recorded examples
Status: done
Wave: 10   Lane: W
Touches: none
Blocked by: 105
Integrates with: 102
Read first: docs/ADVISOR.md#prompt-injection, docs/adr/0014-the-demo-advisor-replays-recorded-answers.md

## Goal
Even if an image slipped past the API and the renderer, the browser would refuse to fetch it. And
the public demo shows what the advisor does without ever calling a model.

## Acceptance criteria
- [x] `next.config.ts` adds a `Content-Security-Policy` header with `img-src 'self' data: blob:`,
      `connect-src 'self'` and `frame-ancestors 'none'`, plus exactly what the browser Sentry SDK
      in `lib/sentry.ts` needs — a tunnel route through this origin is preferred over allowing
      Sentry's host. `script-src` is not tightened here; Next's inline scripts need nonces, and
      that is its own ticket.
- [x] A test asserts the header on every route and the absence of any wildcard in `img-src` or
      `connect-src`.
- [x] **`'self'` stays trustworthy** — the EchoLeak lesson. Tests assert that `route.ts` only ever
      forwards to `INTERNAL_API_URL` whatever path it is given (including encoded `//` and
      absolute-URL tricks), keeps `redirect: "manual"`, and that no API route issues a redirect to
      another host. A same-origin endpoint that fetched or redirected elsewhere would turn
      `img-src 'self'` into a way out.
- [x] Under `NEXT_PUBLIC_DEMO`, `/advisor` renders the recorded conversations in
      `lib/advisor-examples.json` through 105's renderer, read-only, with no question box and a
      plain label: recorded on the demo's synthetic data; this demo cannot ask new questions.
- [x] `advisor-examples.json` starts with one hand-written synthetic example until 102's
      `make eval-examples` replaces it.
- [x] Tests: demo mode renders the examples and no input; the examples pass through the same safe
      renderer; the CSP header test.

## Files
- `web/next.config.ts`
- `web/src/lib/advisor-examples.json` (new)
- `web/src/components/advisor/demo-examples.tsx` (new)
- `web/src/app/(dashboard)/advisor/page.tsx`
- `web/src/components/advisor/demo-examples.test.tsx`

## Done — 2026-09-28

- CSP: `img-src 'self' data: blob:; connect-src 'self'; frame-ancestors 'none'; object-src 'none';
  base-uri 'self'; form-action 'self'`. The web app's Sentry reports from the server only, so it
  needs no allowance and no tunnel. Checked live: the header is served, the app and the dev
  reload socket run under it, and a planted `https://` image fires an `img-src` violation.
- **Found: FastAPI's trailing-slash redirect.** `/accounts/` answered 307 to an absolute URL built
  from the request's host — behind the proxy, the private API's — so a same-origin path
  redirected off-origin. The API now runs with `redirect_slashes=False`, and a contract test walks
  every GET route with and without the slash and fails on any 3xx (it fails without the fix).
- The proxy refuses any upstream 3xx with a 502 and no `Location`, and forwards only to
  `INTERNAL_API_URL` whatever the path — tested with scheme, `//`, `@`, `..` and encoded forms.
- The demo's `/advisor` is chosen at build time (`IS_DEMO`), renders recorded examples through
  105's `TurnCard` with no question box and no flag control, and makes no API call.
- The first example was produced by the real loop with the scripted model on synthetic data and
  read back through the conversation endpoint, so its figure offsets are the server's own.
