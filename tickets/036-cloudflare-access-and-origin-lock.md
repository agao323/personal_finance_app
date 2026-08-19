# 036 — Cloudflare Access and origin lock
Status: in-progress
Wave: 3   Lane: —
Blocked by: 035, 008
Read first: docs/SECURITY.md#auth, docs/ARCHITECTURE.md#request-path

## Goal
The real app reachable only through Cloudflare Access, at `<domain>`, with the API
verifiably private.

## Acceptance criteria
- [ ] Cloudflare Access application on `<domain>` with a policy allowing exactly the household identities
- [ ] **The API remains private** — no public Fly address, verified by attempting to reach it from outside
- [x] Next.js validates the `Cf-Access-Jwt-Assertion` JWT and rejects requests that did not pass Access
- [x] HSTS and `noindex` on the real deployment
- [ ] Verified: an unauthenticated request from a clean browser cannot reach the app
- [x] `docs/adr/0002-auth.md` written while deciding
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

## Status — 2026-08-18: origin side done, four manual steps remain

Everything authorable is written and tested.

- `web/src/lib/access.ts` verifies `Cf-Access-Jwt-Assertion` against Cloudflare's
  published keys — signature, issuer *and* audience — and `proxy.ts` returns 403 when
  it does not verify. Disabled when unconfigured so local dev and the demo still run;
  both `CF_ACCESS_TEAM_DOMAIN` and `CF_ACCESS_AUD` must be set, because an audience with
  no issuer accepts a token from any Access tenant and an issuer with no audience
  accepts one minted for a different app.
- HSTS, `X-Robots-Tag`, `X-Frame-Options`, `nosniff` and a referrer policy on every
  response, set at the origin rather than only at the edge.
- `docs/adr/0002-auth.md` — the decision, the alternatives, and an empty verification
  table.
- `scripts/check_fly_api_private.sh` already covers "the API app declares no public
  service" and runs in CI.

**These need your Cloudflare dashboard, so they are yours to run.** Until they are done
there is no Access application, which is why 024 stays blocked.

1. **Create the Access application** on `allofmymoney.com` with an *Emails* policy
   listing exactly the household's addresses — not a domain rule.
2. **Copy the Application Audience tag** and set it:
   ```bash
   fly secrets set CF_ACCESS_AUD=<the aud tag> -a pfa-web
   ```
3. **Run the verification steps** in `docs/runbooks/access-verification.md`. All six.
   Step 3 (`fly ips list -a pfa-api` shows no public address) and step 4 (the origin
   returns 403 to a request from inside the machine) are the two that actually prove
   the lock.
4. **Record the results** in the table at the bottom of `docs/adr/0002-auth.md`.

`CF_ACCESS_TEAM_DOMAIN` in `fly.web.toml` assumes your team domain is
`allofmymoney.cloudflareaccess.com` — correct it if Cloudflare gave you a different one.
