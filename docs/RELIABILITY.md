# Reliability

How the app stays up, tells you when it isn't, keeps its data, and how an agent boots and
inspects it. Procedures with steps are in [runbooks](#runbooks).

## Boot and inspect the app (for agents)

You need Docker, `make`, `uv` and `pnpm`. Nothing to sign in to locally.

| Goal | Command | What you get |
|---|---|---|
| Run the full stack | `make dev` | Postgres, API and web with hot reload on both, at http://localhost:3000. Copies `.env.example` to `.env` if missing. Migrations run inside the API's dev command |
| Load data | `make seed` | 30 months of synthetic history: nine accounts, a 50%-owned rental, a mid-history stake change, a closed account, matched transfers, uncategorised rows, a card with credits. Resets the database, leaving household members alone. Refuses a database whose `data_marker` says real |
| Watch it | `make logs` | Every service's logs; `docker compose logs -f api` for one |
| Prove the request path | `make smoke` | Builds the **deploy-shaped** images and asserts: API not published to the host, web reaches API internally, `/api/ready` works end to end, an upstream 404 passes through |
| Drive it in a browser | `make e2e` | Playwright against the deploy-shaped stack, migrated and seeded first. Failures leave traces in `web/test-results/` |
| See it | `CAPTURE_SCREENSHOTS=1 make e2e` | Regenerates `docs/images/*.png` via `web/e2e/screenshots.spec.ts` |
| Talk to the API directly | `curl localhost:3000/api/ready` | Always through the web origin — the API has no port on the host in the deploy-shaped stack |

Who you are locally: `DEV_IDENTITY_EMAIL` in `.env` names a `users` row. It is ignored on
any https origin and whenever Access is configured — absence of a check must never read as
a passing one ([SECURITY.md](SECURITY.md#locally-and-on-the-demo)).

Every figure you see is synthetic. Never point the local stack at production, and never
open `data/` — see [SECURITY.md](SECURITY.md#handling-real-data-during-development).

### Pitfalls

Things that will otherwise cost you twenty minutes each:

- **Adding a dependency needs a container rebuild.** `docker compose restart` reuses the
  old image and the new import fails at runtime. `make dev` rebuilds, as does
  `docker compose up -d --build <service>`.
- **A brand new route directory** under `web/src/app` is often missed by the dev server's
  file watcher through the bind mount, and 404s until `docker compose restart web`.
- **The compose project is always named `pfa`** (`docker-compose.yml`), so every checkout
  and worktree of this repo shares one set of containers and ports 3000 and 5432. Running
  `make dev` in a second worktree recreates the first one's containers. To run the suites
  against a stack that is already up, use `CI=true make test`, which skips starting
  Postgres.
- **The deploy-shaped stack has no migration step.** On Fly that is the release command;
  compose has no equivalent. `make e2e` runs `alembic upgrade head` explicitly, and the dev
  override runs it inside the API's command.

## Health vs ready

| Endpoint | Answers | Touches the DB? | Probed by |
|---|---|---|---|
| API `/health` | the process is alive | **No** | Fly, every 15 s |
| API `/ready` | the database is reachable (`{"database": true}`, else 503) | Yes | `make smoke`, `curl …/api/ready` after a deploy |
| Web `/healthz` | the Next.js server is alive | No | Fly |

Fly probes `/health` only. Probing `/ready` would let a transient database blip restart
otherwise-healthy instances. Both stay public (no identity required): a health check that
needs an identity cannot report that the app is unhealthy, and Fly's prober carries no
Access assertion (`test_contract.py`, `PUBLIC_PATHS`). Tested in `test_health.py`,
including that `/health` never touches the database.

**A deployment with Access unconfigured does not start** (ticket 047a). Refusing each
request would be correct and one request too late; an operator should learn from a failed
release, not a support conversation.

## Cold starts

Measured, not guessed — ticket 048 found the 5.5 s first load was **4.2 s of Node starting
Next.js**, not Neon (287 ms cold connect, 43 ms pooled):

- **`pfa-web` keeps one machine running** (`min_machines_running = 1`). The boot now
  happens on deploys, where the release is already waiting, instead of in front of a person.
- **`pfa-api` is always on** — `.internal` has no Fly proxy to wake it ([hosting](design-docs/hosting.md)).
- **Neon autosuspends after 5 minutes.** `pool_pre_ping` discards connections that died
  during a suspend, so the first query after idle is slower, not an error.
- **The demo sleeps**; the edge cache is what makes its first visit fast
  ([demo caching](design-docs/hosting.md#demo-caching)).

## Migrations

- **Run as a Fly `release_command`** (`alembic upgrade head` in `fly.api.toml`), before
  the new version takes traffic. A broken migration aborts the release rather than
  half-migrating under live requests; two booting machines never race one migration.
- **Deploy the API first** (`make deploy-api`, then `make deploy-web`) — the web app
  reaches it over the private network.
- **Human-reviewed, one in flight at a time** ([PLANS.md](PLANS.md#how-to-work-a-plan)).
  `make migrate m="…"` proposes; a person reads every line. `make downgrade` rolls back one
  locally. A dropped table is not recoverable by a downgrade with its rows intact.
- Tests migrate a real Postgres with `alembic upgrade head`, never `create_all()`, so a
  broken migration cannot ship green.

## Errors and logs

- **Logs:** structlog, JSON, one line per request with request id, method, path, status,
  duration (`middleware.RequestContextMiddleware`). **Financial values are never logged**:
  `logging.py` redacts every monetary key on the way out — a filter the caller cannot forget
  to apply — and `test_logging.py` asserts it through nested dicts, lists and tuples.
  Structured logs are useless if reading them means reading your own balances out of a log
  aggregator.
- **Errors:** Sentry on both services, DSN from the environment, cleanly disabled when
  unset so development and tests never emit. Request bodies are never captured, and any
  monetary field surviving elsewhere in an event goes through the same redaction
  (`observability.py`; web: `lib/sentry.ts`, `instrumentation.ts`).
- **Production:** `fly logs -a pfa-web` / `-a pfa-api`; `fly ssh console -a pfa-api` —
  there is no URL to curl the API from a laptop, by design. An Access rejection logs its
  reason and the issuer it tried while the response stays a bare 403
  ([ADR 0002](adr/0002-auth.md#what-the-first-attempt-taught-us)).

## Backups and the restore drill

Two layers, and nothing we operate holds an offsite copy ([ADR 0008](adr/0008-local-backups.md)):

1. **Neon's automatic backups and point-in-time recovery.** Free, and ask nothing of anyone.
   They share fate with the Neon account, which is why there is a second layer.
2. **`make backup`** writes every table to `data/backups/pfa-<date>.json` on the owner's
   machine, whose own backup carries it from there. Reads `BACKUP_DATABASE_URL` (the
   **unpooled** Neon string) from `.env`.

**No schedule.** A manual command that is actually run beats a scheduled one that silently
stops — the previous design's job failed every night for five weeks before anyone switched
it off. **An untested export is not a backup:** `make restore f=…` loads one into the local
database (never production by default), and [api/scripts/restore.md](../api/scripts/restore.md)
is the drill. The first drill (2026-09-27, synthetic data) found a real foreign-key ordering
bug. **A drill against a production export is still pending, and it gates real data**
(tickets 024 and 075).

Only `balance_snapshots` is irreplaceable; everything else is bank CSVs or hand-typed
rows ([snapshots](design-docs/snapshots-and-carry-forward.md)). `GET /export` is the escape
hatch that works from a browser.

## Runbooks

| Runbook | When |
|---|---|
| [going-live.md](runbooks/going-live.md) | Everything that needs an account or a dashboard, in order: secrets, Access, backups, sheet import, demo, clean-clone check |
| [access-verification.md](runbooks/access-verification.md) | After any change to Fly config, the Access policy, or DNS |
| [api/scripts/restore.md](../api/scripts/restore.md) | Taking a backup, running the restore drill, restoring for real |
| [doc-gardening.md](runbooks/doc-gardening.md) | Weekly: an agent compares doc claims against the code |
