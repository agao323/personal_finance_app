# 008 — Deploy the skeleton to Fly and Neon
Status: in-progress
Wave: 0   Lane: —
Blocked by: 007
Read first: docs/ARCHITECTURE.md#hosting, docs/ARCHITECTURE.md#request-path

## Goal
`/health` green on the public internet, on a real domain, with TLS, against Neon, with
migrations wired as a release command. The app is an empty skeleton. That is the point.

## Acceptance criteria
- [x] `fly.api.toml` and `fly.web.toml`
- [x] **The API app declares no public services** — reachable only over the Fly private network
- [ ] Neon project provisioned; **pooled** connection string stored in Fly secrets — BLOCKED: needs an account
- [x] Migrations run as a Fly **release command**, not on boot
- [ ] Custom domain on the web app with TLS, HSTS, and `noindex` — BLOCKED: needs a registered domain (`noindex` already shipped in 004's layout)
- [ ] Web app reaches the API over the private network; verified from outside that the API is unreachable — BLOCKED: needs a deploy. **Deviation:** uses `.internal`, not `.flycast` — flycast requires a services block, which would make public exposure a misconfiguration away rather than impossible. See ADR 0001.
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

## Status — 2026-08-17

Every artifact is written and verified locally. Three criteria are blocked on account
creation and a domain purchase, which need a payment method:

1. Create a Neon project and copy the **pooled** connection string.
2. Register a domain (Cloudflare Registrar) and add it to Cloudflare.
3. `brew install flyctl && fly auth signup`.

Then follow the deploy sequence in the README. Reopen this ticket to check off the
remaining three and confirm `fly ips list -a pfa-api` is empty.
