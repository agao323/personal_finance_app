# Hosting

**Neon** for Postgres, **Fly.io** for both services, **Cloudflare** for DNS, TLS, and
Access. Decided in [ADR 0001](../adr/0001-hosting.md), which has the alternatives
(`.flycast`, Fly Postgres, Neon branches, migrations on boot, Kubernetes) and the TLS and
apex amendments.

| App | Config | Public? | Machines |
|---|---|---|---|
| `pfa-web` | `fly.web.toml` | Yes — the only public entry point | `min_machines_running = 1` since ticket 048 |
| `pfa-api` | `fly.api.toml` | **No** — no `[http_service]`, no `[[services]]`, no ports | Always on; `.internal` has no Fly proxy to wake it |
| `pfa-demo-web` | `fly.demo-web.toml` | Yes, `demo.<domain>` | Sleeps (`min_machines_running = 0`); the edge cache covers the cold start |
| `pfa-demo-api` | `fly.demo-api.toml` | No | Always on |

## Why Neon, not a self-run Postgres

[SECURITY.md](../SECURITY.md#backups) argues that moving a financial picture out of Google
Sheets is a durability downgrade until backups are proven. Operating a single-node Postgres
VM would maximise exactly that downgrade. Neon's automatic backups and point-in-time
recovery, *plus* a full local export (`make backup`, ticket 017,
[ADR 0008](../adr/0008-local-backups.md)), give two independent layers for $0 on the free
tier. (The second layer was a nightly encrypted `pg_dump` to R2 until ADR 0008 replaced it.)

Practical notes:

- Use Neon's **pooled** connection endpoint (the host containing `-pooler`).
  `api/app/db.py` is configured for it: PgBouncer runs in transaction mode, so psycopg's
  implicit prepared statements are off (`prepare_threshold=None`), `pool_pre_ping` discards
  connections that died during an autosuspend, and the pool stays small because PgBouncer
  already pools. The backup export and `pg_dump`-style tools want the **unpooled** string.
  See [references/neon-pooling-llms.txt](../references/neon-pooling-llms.txt).
- Neon autosuspends on idle. The first request after a suspend pays a cold start
  ([RELIABILITY.md](../RELIABILITY.md#cold-starts)).
- Real and demo are **separate Neon projects**, not two branches of one. Branches share a
  project and an account; that is a weaker boundary than the separate-credentials
  guarantee the demo depends on. Branching is the right tool for dev/prod convenience and
  the wrong one for a public-facing trust boundary ([ADR 0003](../adr/0003-demo-isolation.md)).
- Free-tier allowances are **per project**: 0.5 GB storage, 100 CU-hours/month, 5 GB
  egress, 10 branches (confirmed against Neon's 2026 free plan). Two projects on the free
  plan cover this app. Storage and egress are not close to binding — a household's finance
  data is tens of megabytes.
- **Compute hours are the one limit worth watching, and only on the demo.** At minimum
  sizing that budget is roughly 400 wall-clock hours of awake compute per month against a
  ~730-hour month. The real app, used by one household with a 5-minute autosuspend, will
  not come near it. The public demo can: it is indexed by design, and a crawler hitting it
  regularly keeps the database permanently awake. The fix is the same thing that makes the
  demo good — [demo caching](#demo-caching).
- A **branch of the real project** is the right scratch target for a restore you want to
  inspect before trusting — that is exactly what branches are for. The routine restore
  drill uses the local Docker database instead ([api/scripts/restore.md](../../api/scripts/restore.md)).

## Fly

- **Migrations run as a Fly release command**, not on boot — two booting instances would
  race the same migration, and a failed release command aborts the deploy instead of
  half-migrating under live requests.
- The API has **no public address**, reached at `http://pfa-api.internal:8000` over Fly's
  private IPv6 network ([request-path.md](request-path.md)). `fly ips list -a pfa-api`
  returning nothing is most of the security posture in one command. Notes:
  [references/fly-private-networking-llms.txt](../references/fly-private-networking-llms.txt).
- The web app used to sleep, and the 5.5-second cold start landed on essentially every
  visit, so since ticket 048 one machine stays up ([RELIABILITY.md](../RELIABILITY.md#cold-starts)).
- Cloudflare → Fly TLS is **Full (strict)**, failing closed rather than degrading
  ([ADR 0001](../adr/0001-hosting.md), 2026-08-18 amendment).

## Demo caching

The demo is read-only over a static synthetic dataset, which means nearly every response can
be cached at the edge with a long TTL. Doing so buys three things at once:

1. **Keeps demo compute inside the free tier** — crawlers and repeat visitors are served by
   Cloudflare and never wake Neon.
2. **Removes the cold start on a first visit.** Neon autosuspends after 5 minutes idle and
   the demo's Fly machine auto-stops, so an uncached click on a fully idle demo pays both. A
   public link that takes several seconds to render a blank page is a broken link as far as
   whoever clicked it is concerned. A cached page is instant.
3. Costs nothing and needs no extra infrastructure.

Cache at the Cloudflare layer on the demo hostname only. **The real app must never be cached
at the edge** — it is behind Access and its responses are personal. Setting this up is the
open half of ticket 037.

## Cost

Roughly $4–7/month plus ~$12/year for the domain: one always-on shared-cpu-1x machine each
for the API and (since 048) the web app, with Neon, Cloudflare and Sentry on free tiers
([ADR 0001](../adr/0001-hosting.md#consequences)). The demo adds its always-on API machine
once it exists. Verify current pricing before committing — these tiers drift.

## Why not Kubernetes

The learning goal explicitly includes containers and orchestration, so this needs a real
answer.

K8s for a single-household app is the wrong tool by roughly two orders of magnitude. It
would consume weeks that v1 needed, and the operational complexity it adds buys nothing at
one household of traffic — there is no scaling event to absorb, no rolling deploy worth
orchestrating, no bin-packing problem to solve.

The sequencing that serves both goals:

- **Now:** Docker + Fly.io + managed Postgres. You still write Dockerfiles and handle
  migrations, secrets, health checks, private networking, and release commands. Real, not a
  sink.
- **Later, optional, after the app works:** redeploy the same app to k3s on a VPS purely as
  a learning exercise. The written retro of what it cost versus what it bought is a better
  artifact than the cluster itself.

The things that will actually teach the most about databases live in the app, not the
infra: hand-reviewed migrations, the effective-dated ownership model, and the snapshot
history.

No Terraform either: the infrastructure is four TOML files and a Makefile, and anything
more would be operational work that exists to be operated.
