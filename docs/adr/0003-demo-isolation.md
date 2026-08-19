# ADR 0003 — The demo is a separate deployment against a separate Neon project

Status: accepted · 2026-08-19 · Ticket 037

## Context

There is a public demo at `demo.allofmymoney.com`, unauthenticated and indexed, showing
the synthetic dataset from ticket 018. The real app at `allofmymoney.com` holds one
household's actual finances.

**The failure mode is handing out a public link that shows real balances.** That is the
worst thing this project can do, and it is worth more caution than anything else in it.

## Decision

**Separate Fly apps, and a separate Neon project.** Not a runtime flag over one
database. Not a Neon branch of the real project.

Four deployables: `pfa-api` / `pfa-web` against the real Neon project, and
`pfa-demo-api` / `pfa-demo-web` against a different one. The demo's `DATABASE_URL`
holds credentials that **cannot authenticate** to the real database.

The isolation is that fact and nothing else. Everything below is defense in depth.

## Alternatives considered

**A runtime flag over the real database.** `DEMO_MODE=true` returning synthetic figures
from the same deployment. Rejected outright: it is one bad conditional, one missed code
path, or one mis-set environment variable away from serving real balances to the public
internet — and the mistake would look like working software. There is no test that
makes this safe, because the property you want is "the data is not reachable", and here
it is reachable by construction.

**A Neon branch of the real project.** Tempting, and it is what branches are for in
other contexts — the backup restore drill uses one. Rejected here because a branch
shares a project and an account with its parent. The credentials are issued by the same
project, the console shows both together, and "delete the wrong thing" is a two-click
mistake. For the one boundary that must not be weak, sharing an account is weak.

**A separate database inside the same Neon project.** Same objection, less clearly.
Same credentials reach both.

## Consequences

**Two Neon projects on the free tier.** Neon's free plan allows this. If it ever stops,
the demo moves to a paid project or goes away — it does not move into the real project.

**Reseeding the demo is a deploy-time action**, not a cron. The dataset is fixed and
deterministic (seed `20260818`), so there is nothing to keep fresh.

**The demo is read-only**, enforced three ways, in descending order of how much weight
each carries:

1. Its credentials cannot reach the real database. *This is the boundary.*
2. `DEMO_MODE=true` rejects every mutating verb in middleware — so a route added later
   is covered without anyone remembering. `api/tests/test_demo_mode.py` walks the live
   app and asserts no declared route is writable.
3. `NEXT_PUBLIC_DEMO=true` is a **build arg**, so the demo bundle does not contain the
   sign-in path at all rather than containing it and declining to use it.

Allowing writes against synthetic data would be safe in principle and adds a public
unauthenticated write surface needing rate limiting and a reseed cron. Noted in
SECURITY.md as a fast follow, not a v1 commitment.

**The demo is not behind Cloudflare Access**, which is the whole point, and
`fly.demo-web.toml` deliberately sets no `CF_ACCESS_*` variables. A CI step asserts
that — with comments stripped first, because the config explains *why* it sets none and
a naive grep matches the explanation.

**`X-Robots-Tag` and the `robots` metadata invert for the demo.** The real app is
`noindex, nofollow` and the demo is indexed; both derive from the same build-time flag,
so they cannot disagree.

**Edge caching does two jobs.** The dataset is static and read-only, so Cloudflare
caches the demo hostname with a long TTL. That keeps demo compute inside Neon's free
CU-hour allowance when crawlers hit an indexed public site, and it removes the cold
start — Neon autosuspends after five minutes idle and Fly machines auto-stop, so an
uncached first visit would otherwise spend several seconds on a blank page and
reasonably be judged broken. **The real hostname is never edge-cached.**

## Verification

`.github/workflows/demo-guard.yml` runs on every push and weekly — weekly because the
secrets can be changed without a push, and a push-only check would not notice someone
repointing the demo at the real project.

It asserts the two database URLs differ, and that their **Neon endpoint ids** differ,
which is what distinguishes a separate project from a branch. Pooled and unpooled hosts
for one project differ only by a `-pooler` suffix, so that is stripped before comparing —
otherwise the same project reads as two. Neither URL is ever printed: a guard that
echoes a connection string into a build log has created the disclosure it exists to
prevent.

It skips rather than fails while `DEMO_DATABASE_URL` is unset, because a permanently red
check for "not built yet" trains people to ignore it — which is the last thing this
particular guard can afford.

| Date | Check | Result |
|---|---|---|
| _pending_ | Demo database contains only synthetic data, verified by connecting to it directly | |
| _pending_ | Demo credentials rejected by the real database | |
| _pending_ | Repeat visit served from Cloudflare cache without waking Neon | |
| _pending_ | Cold first click renders in under 3s | |
| _pending_ | Real hostname returns no cache hit | |
