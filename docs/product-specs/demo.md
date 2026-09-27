# The public demo

The whole app, publicly linkable at `demo.<domain>`, on synthetic data only. The failure
mode is handing out a link that shows real finances, so the boundary is infrastructure, not
a flag. **The code is shipped; the deployment does not exist yet** (TD-005).

## What a visitor gets

- Every screen, read-only, with no sign-in.
- A **permanent banner** above the navigation saying the data is synthetic — not a
  dismissible toast, because one dismissed on the dashboard is gone by the transactions
  screen, where the figures look most like a real person's life.
- A coherent synthetic household: correlated income and spend, a 50%-owned rental, a
  mid-history stake change, a closed account, matched transfers, uncategorised rows, cards
  with credits across cadences. Seeded deterministically (seed `20260818`).
- Fast first loads, because the demo hostname is edge-cached.

## Rules and edge cases

- **Separate Fly apps and a separate Neon project** — not a branch of the real project, not a
  flag over real data. The demo's credentials cannot authenticate to the real database; that
  fact is the boundary ([ADR 0003](../adr/0003-demo-isolation.md)).
- **Every mutating verb is refused (405)**, in middleware, so a route added later is covered
  without anyone remembering. Defence in depth, not the boundary.
- **The demo bundle contains no sign-in path at all** — `NEXT_PUBLIC_DEMO` is a build arg.
  The API serves a fixed synthetic identity in demo mode.
- The demo Fly config declares **no Cloudflare Access**; CI asserts it (comments stripped
  first, because the config explains why).
- The real app is `noindex, nofollow`; the demo is indexed. Both derive from the same build
  flag, so they cannot disagree.
- **Edge-cache the demo hostname only.** The real app is never edge-cached.
- **Reseeding is a deploy-time action**, not a cron; the seed refuses any database marked
  real.
- Writes against synthetic data would be safe in principle but add a public write surface
  needing rate limiting and a reseed cron — a fast follow, not v1.
- The isolation guard (`demo-guard.yml`) skips until the demo exists, and currently compares
  against a retired secret — TD-007.

## Endpoints

The same API. In demo mode: every `POST`, `PUT`, `PATCH` and `DELETE` answers 405 with an
`Allow` header.

## Code and config

`fly.demo-api.toml`, `fly.demo-web.toml`, `make deploy-demo`, `api/app/middleware.py`
(`DemoReadOnlyMiddleware`), `api/app/config.py` (`DEMO_MODE`), `web/src/lib/demo.ts`,
`web/src/components/demo-banner.tsx`, `scripts/check_demo_isolation.sh`,
`.github/workflows/demo-guard.yml`. Setup steps: [going-live §E](../runbooks/going-live.md#e--ticket-037--the-public-demo).

## Built by

018 (the synthetic generator), 037 (in progress — code done, infrastructure not), 040 (a seed
where Mine / Household reads sensibly), 067 (seeded cards with credits).
