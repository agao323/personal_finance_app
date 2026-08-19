# 037 — Demo deployment
Status: in-progress
Wave: 3   Lane: —
Blocked by: 036, 018
Read first: docs/SECURITY.md#demo-isolation

## Goal
A public demo at `demo.<domain>`: separate Fly apps, **a separate Neon project**, synthetic
seed, writes rejected. The boundary is infrastructure, not a flag.

## Acceptance criteria
- [ ] Separate Fly apps and a **separate Neon project** — not a branch of the real project — for the demo
- [ ] Demo database seeded by the synthetic generator only
- [x] `DEMO_MODE=true` rejects all mutating verbs — defense in depth, **not** the boundary
- [ ] Demo credentials verifiably cannot reach the real database
- [x] No auth on the demo; indexed and publicly linkable
- [x] A banner making it obvious the data is synthetic
- [ ] CI asserts the two database URLs differ **and belong to different Neon projects**
- [ ] **Edge caching on the demo hostname** with a long TTL — the dataset is static and read-only. Verified that a repeat visit is served by Cloudflare without waking Neon.
- [ ] Cold-start budget: a first click on a fully idle demo renders in under 3s; a cached click is instant
- [ ] Confirmed the real app hostname is **never** edge-cached
- [ ] Documented reseed procedure, including cache purge
- [x] `docs/adr/0003-demo-isolation.md`
- [x] Tests: CI guard workflow for the URL assertion; functional asserting every mutating verb returns 405 under `DEMO_MODE`

## Files
- `fly.demo-api.toml`
- `fly.demo-web.toml`
- `.github/workflows/demo-guard.yml`
- `docs/adr/0003-demo-isolation.md`

## Notes
The most security-sensitive ticket in the project. The failure mode is handing out a public
link that shows real finances.

Verify by connecting to the demo database directly and confirming only synthetic data is
present. Separate Neon **projects**, not branches — branches share a project and an account,
which is a weaker boundary than separate credentials, and this is the one boundary that must
not be weak.

The demo is read-only in v1. Allowing writes against synthetic data is safe in principle but
adds a public unauthenticated write surface needing rate limiting and a reseed cron — noted in
SECURITY.md as a fast follow, not a v1 commitment.

Read-only is also what makes the edge caching trivial, and the caching is doing two jobs: it
keeps demo compute inside Neon's free CU-hour allowance when crawlers hit an indexed public
site, and it removes the cold start on an uncached first visit. Neon autosuspends after 5
minutes idle and Fly machines auto-stop — without caching, someone opening the demo link cold
waits several seconds on a blank page and reasonably concludes it's broken.

## Status — 2026-08-19: code done, infrastructure is yours

Everything authorable is written and tested.

- **`DEMO_MODE` now does something.** It was configured and inert — read by `Settings`,
  used by nothing. `DemoReadOnlyMiddleware` rejects every mutating verb with a 405 and
  an `Allow` header. In middleware, not per route, so a route added later is covered by
  default; `test_demo_mode.py` walks the live app and asserts no declared route is
  writable, rather than trusting a hand-written list.
- **The banner** is permanent and above the navigation, not a dismissible toast — one
  dismissed on the dashboard is gone by the transactions screen, which is where the
  figures look most like a real person's life.
- **`fly.demo-api.toml` / `fly.demo-web.toml`**, with `NEXT_PUBLIC_DEMO` as a *build
  arg* so the demo bundle contains no sign-in path at all, and deliberately no
  `CF_ACCESS_*`.
- **`scripts/check_demo_isolation.sh`** compares Neon *endpoint ids*, which is what
  separates a project from a branch. It strips the `-pooler` suffix first — otherwise a
  pooled and an unpooled URL for one project read as two. Four self-tests in
  `test_guards.sh`.
- **`.github/workflows/demo-guard.yml`**, on every push and weekly. Weekly because the
  secrets can change without a push. It skips rather than fails while
  `DEMO_DATABASE_URL` is unset — a permanently red check for "not built yet" trains
  people to ignore it.
- **`docs/adr/0003-demo-isolation.md`**, with the alternatives and an empty verification
  table.
- `make deploy-demo`.

A comment nearly defeated a guard again: the demo web config explains *why* it sets no
`CF_ACCESS_*` variables, and the naive grep matched the explanation. Comments are
stripped first now — the same trap `check_fly_api_private.sh` already documents.

### Yours to run

1. **Create a second Neon project** — a *project*, not a branch. Copy its pooled
   connection string.
2. **Create the Fly apps and set secrets:**
   ```bash
   fly apps create pfa-demo-api && fly apps create pfa-demo-web
   fly secrets set -a pfa-demo-api DATABASE_URL='<the demo project pooled URL>'
   fly secrets set -a pfa-demo-api SESSION_SECRET="$(openssl rand -base64 32)"
   make deploy-demo
   fly certs add -a pfa-demo-web demo.allofmymoney.com
   ```
3. **Seed it**, against the demo database only:
   ```bash
   fly ssh console -a pfa-demo-api -C "python scripts/seed_synthetic.py"
   ```
4. **DNS + caching.** A `demo` CNAME to the Fly app, proxied. A Cache Rule on
   `demo.allofmymoney.com` with a long edge TTL. **Confirm no cache rule matches the
   apex** — the real app must never be edge-cached.
5. **Add the `DEMO_DATABASE_URL` GitHub secret**, which switches the guard from skip to
   enforce.
6. **Run the five checks** in ADR 0003's table and record the results, including the
   cold-start budget (under 3s on a fully idle demo) and that a repeat visit is served
   by Cloudflare without waking Neon.

### Still open

- [ ] Separate Fly apps and a separate Neon project
- [ ] Demo database seeded by the synthetic generator only
- [ ] Demo credentials verifiably cannot reach the real database
- [ ] Edge caching, verified
- [ ] Cold-start budget
- [ ] Real hostname confirmed never edge-cached
- [ ] Documented reseed procedure, including cache purge
