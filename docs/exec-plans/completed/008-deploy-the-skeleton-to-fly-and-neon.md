# 008 — Deploy the skeleton to Fly and Neon
Status: done
Wave: 0   Lane: —
Blocked by: 007
Read first: docs/ARCHITECTURE.md#hosting, docs/ARCHITECTURE.md#request-path

## Goal
`/health` green on the public internet, on a real domain, with TLS, against Neon, with
migrations wired as a release command. The app is an empty skeleton. That is the point.

## Acceptance criteria
- [x] `fly.api.toml` and `fly.web.toml`
- [x] **The API app declares no public services** — reachable only over the Fly private network
- [x] Neon project provisioned; **pooled** connection string stored in Fly secrets
- [x] Migrations run as a Fly **release command**, not on boot
- [x] Custom domain on the web app with TLS and `noindex`. **HSTS is ticket 036** — Cloudflare fronts the origin, so the header belongs with the Access configuration, not here.
- [x] Web app reaches the API over the private network; verified from outside that the API is unreachable. **Deviation:** `.internal`, not `.flycast` — flycast requires a services block, which would make public exposure a misconfiguration away rather than impossible. See ADR 0001.
- [x] `auto_stop_machines` enabled so idle cost stays near zero
- [x] No secret in the repo; `.env.example` documents each one
- [x] Deploy documented in the README as a runnable sequence
- [x] `docs/adr/0001-hosting.md` written **while** deciding, not after
- [x] Tests: a CI job asserting `fly.api.toml` declares no `[[services]]` or `http_service` block

## Files
- `fly.api.toml`
- `fly.web.toml`
- `docs/adr/0001-hosting.md`
- `README.md`
- `.github/workflows/ci.yml`

## Notes
This is deliberately ticket 008 and not ticket 029. Every unknown in "deploy it into a live
environment" — Fly private networking, Neon pooling, release-command migrations, TLS,
secrets — surfaces now, on an empty app, instead of at the end on a full one. That is the
difference between a day and the classic 90%-done month.

Migrations as a release command rather than on boot: on boot, two starting instances race the
same migration.

There is no migration to run yet. Wire the release command anyway and let it no-op — 009 is
the first one that does anything, and you want the mechanism proven before it matters.

## Status — 2026-08-18: done

Live at https://allofmymoney.com. `fly ips list -a pfa-api` returns nothing; the API is
reachable only at `pfa-api.internal:8000` over Fly's private IPv6 network.

Three bugs only a real deploy could find, which is the whole reason this ticket sits at
008 rather than 029:

1. `alembic/` was never copied into the API image, so the release command would have
   failed on the first deploy carrying a migration — every deploy after 009.
2. flyctl resolves `dockerfile` against the config file's directory and `context` from
   its path argument. Without the argument it hunted for a Dockerfile at the repo root
   and uploaded 1.7 GB including `node_modules`. Now behind `make deploy-api`.
3. The bind address. `0.0.0.0` is IPv4-only and Fly's private network is IPv6-only, so
   peers got ECONNREFUSED while the app passed its own loopback health check. `::` was
   IPv6-only here and inverted the failure — 6PN worked, Fly's IPv4 health check went
   permanently critical. `app/serve.py` binds one socket with `IPV6_V6ONLY` cleared.

Still open, both in ticket 036: the site has no authentication in front of it, and no
HSTS header. Fine while it serves 501 stubs; both must land before ticket 024 imports
real history.

## Superseded — 2026-08-17

Every artifact is written and verified locally. Three criteria are blocked on account
creation and a domain purchase, which need a payment method:

1. Create a Neon project and copy the **pooled** connection string.
2. Register a domain (Cloudflare Registrar) and add it to Cloudflare.
3. `brew install flyctl && fly auth signup`.

Then follow the deploy sequence in the README. Reopen this ticket to check off the
remaining three and confirm `fly ips list -a pfa-api` is empty.
