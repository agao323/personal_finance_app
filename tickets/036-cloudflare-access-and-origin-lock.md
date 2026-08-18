# 036 — Cloudflare Access and origin lock
Status: todo
Wave: 3   Lane: —
Blocked by: 035, 008
Read first: docs/SECURITY.md#auth, docs/ARCHITECTURE.md#request-path

## Goal
The real app reachable only through Cloudflare Access, at `<domain>`, with the API
verifiably private.

## Acceptance criteria
- [ ] Cloudflare Access application on `<domain>` with a policy allowing exactly the household identities
- [ ] **The API remains private** — no public Fly address, verified by attempting to reach it from outside
- [ ] Next.js validates the `Cf-Access-Jwt-Assertion` JWT and rejects requests that did not pass Access
- [ ] HSTS and `noindex` on the real deployment
- [ ] Verified: an unauthenticated request from a clean browser cannot reach the app
- [ ] `docs/adr/0002-auth.md` written while deciding
- [ ] Tests: CI job asserting the API app declares no public services; a documented manual verification checklist with the results recorded in the ADR

## Files
- `fly.web.toml`
- `web/src/middleware.ts`
- `docs/adr/0002-auth.md`

## Notes
A Fly app is publicly addressable by default — Access in front of an unlocked origin is a false
sense of security. The BFF topology means there is exactly one Access application, no CORS, and
no second hostname to forget about. The JWT validation is defense in depth in case the API app
is ever given a public address by accident.

Verify the origin lock explicitly and write down how you verified it. "It should be private" is
not the same as having checked.
