# The request path

**The browser only ever talks to `<domain>`.** Next.js route handlers under `/api/*`
proxy to the FastAPI service over Fly's private network. The API has no public address
at all.

```
browser ──► Cloudflare (DNS, TLS, Access) ──► Next.js pfa-web ──/api/* over .internal──► FastAPI pfa-api ──► Neon
```

Decided in [DECISIONS.md](../DECISIONS.md) (2026-08-14, "The browser never calls the API
directly — Next.js is a BFF") and made concrete in [ADR 0001](../adr/0001-hosting.md).

## Why: four consequences, all of them the reason for it

1. **Origin lock is structural.** There is no public API hostname to leave unprotected. A
   Fly app is publicly addressable by default; putting Cloudflare Access in front of a
   reachable origin is a false sense of security. Here there is nothing to reach.
2. **No CORS, anywhere.** Same origin. The API ships no CORS middleware (`api/app/main.py`
   says so at the top), and CI fails if `NEXT_PUBLIC_API_URL` or an absolute API origin
   appears in `web/`.
3. **One Cloudflare Access application, not two.** Access answers unauthenticated requests
   with a redirect to the identity provider. A `fetch()` cannot meaningfully follow that —
   an expired session would surface as an opaque network failure instead of a `401`. With
   the API behind the BFF, only page navigations ever hit Access, which is exactly what
   Access is designed for.
4. **Sessions are simple.** One origin means one cookie scope and no cross-site
   negotiation. Since ticket 047b the app sets no cookie of its own at all; the only one in
   play is Cloudflare's `CF_Authorization` ([SECURITY.md](../SECURITY.md#auth)).

## What it costs

A thin proxy route handler, and a strict split: server-side code knows the internal API
URL, and the browser knows no API URL at all. That split had to be right from ticket 002.

| Where | `INTERNAL_API_URL` |
|---|---|
| Local compose | `http://api:8000` (`.env.example`) |
| Production | `http://pfa-api.internal:8000` (`fly.web.toml`) |
| Demo | `http://pfa-demo-api.internal:8000` (`fly.demo-web.toml`) |

**`.internal`, not `.flycast`.** Flycast would bring load balancing and autostart, but it
needs an `[http_service]` or `[[services]]` block — and the moment one exists, public
exposure is one allocated IP away. The guarantee would move from *structurally impossible*
to *correctly configured*. The cost of `.internal` is that the API machine must stay
running (no Fly proxy to wake it). [ADR 0001](../adr/0001-hosting.md) has the full
trade.

The extra hop per API call is a few milliseconds inside one datacenter, against an attack
surface that shrinks to a single origin.

The two-service split itself is unchanged: two Dockerfiles, two deploys, two ecosystems.

## The code

| File | Role |
|---|---|
| `web/src/app/api/[...path]/route.ts` | The proxy. The only code that reads `INTERNAL_API_URL`. Drops hop-by-hop headers, streams bodies, passes upstream status through (`redirect: "manual"`, `cache: "no-store"`) |
| `web/src/lib/api.ts` | The only fetcher in the browser. Requests relative `/api/*` paths and refuses an absolute URL |
| `web/src/proxy.ts` | Unrelated despite the name: Next 16's renamed middleware, which verifies the Access assertion before rendering ([FRONTEND.md](../FRONTEND.md)) |
| `fly.api.toml` | Declares no `[[services]]`, no `[http_service]`, no `ports` |

## What enforces it

| Check | What it catches |
|---|---|
| `scripts/check_no_public_api_url.sh` | `NEXT_PUBLIC_API_URL` used or assigned, or a hardcoded API origin in `web/src` |
| `scripts/check_fly_api_private.sh` (both API configs) | A public service block or port in `fly.api.toml` / `fly.demo-api.toml` |
| `web/eslint.config.mjs` | `fetch()` anywhere but `lib/api.ts` and the proxy route |
| `make smoke` | The deploy-shaped stack: API not published to the host, web reaches API internally, `/api/ready` works end to end, upstream 404 passes through |
| `fly ips list -a pfa-api` | Production: no v4 or v6 address. Recorded in [ADR 0002](../adr/0002-auth.md#verification) |

The origin still validates the Access JWT — defence in depth, in case the Fly app is ever
given a public address by accident. See [SECURITY.md](../SECURITY.md#why-the-api-has-no-public-address).
