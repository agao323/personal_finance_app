# 004 — Next.js skeleton and BFF proxy
Status: todo
Wave: 0   Lane: —
Blocked by: 003
Read first: docs/ARCHITECTURE.md#request-path

## Goal
The web app has a root layout, a server-side proxy route to the API, a typed fetch helper,
and vitest configured. The browser has no API base URL at all.

## Acceptance criteria
- [ ] Route handler at `web/src/app/api/[...path]/route.ts` proxying to the internal API URL — forwards method, path, query, body, and status; strips hop-by-hop headers
- [ ] `apiFetch` helper calling **relative** `/api/...` paths only. No absolute API origin anywhere in `web/`.
- [ ] Root layout with Tailwind, fonts, and light/dark support
- [ ] A page rendering `/ready` output, proving end-to-end connectivity through Docker
- [ ] Vitest + Testing Library + MSW configured
- [ ] Tests: unit for `apiFetch` URL building; functional for the proxy handler covering method, status, body, and error pass-through; component test for the page
- [ ] `make lint` and `make test` pass

## Files
- `web/src/app/layout.tsx`
- `web/src/app/page.tsx`
- `web/src/app/api/[...path]/route.ts`
- `web/src/lib/api.ts`
- `web/src/lib/api.test.ts`

## Notes
The proxy is the entire reason there is no CORS config, no second Cloudflare Access
application, and no public address on the API. **Do not add `NEXT_PUBLIC_API_URL`.** If one
appears, the architecture has been broken — 006 adds a CI check for exactly this.

Do not hand-write response types — 005 generates them. Use `unknown` temporarily and tighten
in 005.
