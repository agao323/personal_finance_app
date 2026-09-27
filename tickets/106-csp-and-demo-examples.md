# 106 — A content security policy, and the demo's recorded examples
Status: todo
Wave: 10   Lane: W
Touches: none
Blocked by: 105
Integrates with: 102
Read first: docs/ADVISOR.md#prompt-injection, docs/adr/0014-the-demo-advisor-replays-recorded-answers.md

## Goal
Even if an image slipped past the API and the renderer, the browser would refuse to fetch it. And
the public demo shows what the advisor does without ever calling a model.

## Acceptance criteria
- [ ] `next.config.ts` adds a `Content-Security-Policy` header with `img-src 'self' data: blob:`,
      `connect-src 'self'` and `frame-ancestors 'none'`, plus exactly what the browser Sentry SDK
      in `lib/sentry.ts` needs — a tunnel route through this origin is preferred over allowing
      Sentry's host. `script-src` is not tightened here; Next's inline scripts need nonces, and
      that is its own ticket.
- [ ] A test asserts the header on every route and the absence of any wildcard in `img-src` or
      `connect-src`.
- [ ] Under `NEXT_PUBLIC_DEMO`, `/advisor` renders the recorded conversations in
      `lib/advisor-examples.json` through 105's renderer, read-only, with no question box and a
      plain label: recorded on the demo's synthetic data; this demo cannot ask new questions.
- [ ] `advisor-examples.json` starts with one hand-written synthetic example until 102's
      `make eval-examples` replaces it.
- [ ] Tests: demo mode renders the examples and no input; the examples pass through the same safe
      renderer; the CSP header test.

## Files
- `web/next.config.ts`
- `web/src/lib/advisor-examples.json` (new)
- `web/src/components/advisor/demo-examples.tsx` (new)
- `web/src/app/(dashboard)/advisor/page.tsx`
- `web/src/components/advisor/demo-examples.test.tsx`
