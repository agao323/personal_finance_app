# Architecture

## Shape

```
        ┌────────────────────────── Cloudflare ──────────────────────────┐
        │  DNS · TLS · HSTS · Access policy (household identities only)  │
        └───────────────────────────────┬────────────────────────────────┘
                                        │   <domain> is the only public origin
                                        ▼
   browser ───────────────►  ┌──────────────────────────────┐
   (one origin, ever)        │  Next.js  (web/)             │
                             │  pages  +  /api/* BFF proxy  │
                             └───────────────┬──────────────┘
                                             │  Fly private network (.internal)
                                             ▼
                             ┌──────────────────────────────┐
                             │  FastAPI  (api/)             │  ← no public address
                             └───────────────┬──────────────┘
                                             │
                                             ▼
                             ┌──────────────────────────────┐
                             │  Neon Postgres               │
                             └──────────────────────────────┘

        Pydantic models ──► openapi.json ──► openapi-typescript ──► web/src/lib/api-types.ts
```

Two deployments of the same code:

| | real | demo |
|---|---|---|
| host | `<domain>` | `demo.<domain>` |
| auth | Cloudflare Access | none (public) |
| database | real Neon project | **separate Neon project**, synthetic seed |
| writes | yes | rejected at the API layer |
| indexing | `noindex` | indexed |

The demo deployment holds credentials that cannot reach the real database. This is the
security boundary — not a feature flag. See [SECURITY.md](SECURITY.md#demo-isolation).

## Request path

**The browser only ever talks to `<domain>`.** Next.js route handlers under `/api/*` proxy
to FastAPI over Fly's private network (`.internal`); the API has no public address. That is
what makes the origin lock structural, removes CORS, and keeps Cloudflare Access to one
application. Design and enforcement: [design-docs/request-path.md](design-docs/request-path.md).

## The API contract

**The Pydantic models are the contract.** `openapi.json` is emitted from them and
`web/src/lib/api-types.ts` is generated from that; `make types-check` fails on drift. Nobody
hand-writes a spec or a response type. Design, rules and the re-freeze procedure:
[design-docs/api-contract.md](design-docs/api-contract.md).

## Users and ownership

Every net worth figure is ownership-adjusted. Stakes are effective-dated, half-open, sum
to ≤ 100% on any date, and every account gets an explicit 100% row at creation — there is
no implicit default. Both users see every account; only the money splits, through the
**Mine / Household** toggle. Spend and runway burn are never split by ownership. Design,
invariants and tests: [design-docs/ownership-and-rounding.md](design-docs/ownership-and-rounding.md).

### Ownership is applied in exactly one place

`services/ownership.adjust()` applies every stake and is the only place ownership-adjusted
money is rounded. No net worth figure is computed from raw balances.
[Details](design-docs/ownership-and-rounding.md#ownership-is-applied-in-exactly-one-place).

## Money

`Decimal` in Python, `NUMERIC(19,2)` in Postgres, **integer cents** over the wire. Never
float. [Why 2dp, and the guards](design-docs/ownership-and-rounding.md#money).

### Rounding

Round half-up, per account, immediately after applying the stake — then sum, so the total
always equals the rows above it. [The rule and every other `quantize`](design-docs/ownership-and-rounding.md#rounding).

## Data model

Twelve tables; the v1 eleven were created in one hand-reviewed migration so Wave 2's lanes
could not collide. Liabilities are stored positive; current balance is derived from the
latest snapshot, never stored. Every table, why it is shaped that way, and the migration
history: [design-docs/data-model.md](design-docs/data-model.md). Columns:
[generated/db-schema.md](generated/db-schema.md).

### `balance_snapshots` and carry-forward

Every balance write appends a snapshot; history that isn't captured is lost. A series
carries balances forward at most 90 days before flagging them stale, and `closed_at`
stops an account counting from that date.
[design-docs/snapshots-and-carry-forward.md](design-docs/snapshots-and-carry-forward.md).

### Closed accounts and carry-forward

See [the design doc](design-docs/snapshots-and-carry-forward.md#closed-accounts-and-carry-forward).

### `transactions`
```
external_id (nullable, unique per account), account_id, posted_at, amount, merchant,
description, category_id, category_source, transfer_group_id (nullable)
```

`external_id` + account is the idempotency key. Ingestion is **upsert, never insert**.
Duplicate transactions after a re-sync are the single most common bug class in this category
of app; design it out on day one rather than debugging it later.

Where the source provides no id, `external_id` is derived deterministically from the row's
content **plus an occurrence index** within `(account, posted_at, amount, merchant)`. The
index matters: two coffees at the same shop on the same day for the same amount are two real
transactions that a naive content hash would silently collapse into one.

**Sign convention: outflows are negative, inflows positive.** Institutions disagree about
this, so CSV import carries a per-mapping sign-normalisation step.

`category_source` (`import | rule | manual`) records where a category came from — so
re-running rules never clobbers a human decision.

### Transfers

A transfer from checking to brokerage is not spending. If it shows up as spending, every
number on the dashboard loses credibility, and runway is wrong in the direction that matters.

Two mechanisms:

- **`categories.kind`** — `income | expense | transfer`. Spend rollups filter to `expense`.
  Income is classified so it stays *out* of the rollups; it isn't displayed in v1.
- **`transactions.transfer_group_id`** — nullable, links the two sides of a matched pair.
  Set by hand in v1 from the transactions screen. Automatic pair detection is a Later ticket.

### `categories` + `categorization_rules`
Imported categories are mediocre. A user-editable rule set (merchant pattern → category,
ordered, first match wins) is what makes the spend breakdowns trustworthy enough to act on.
Without it every spending chart is subtly wrong and the app quietly stops getting used.

Manual per-transaction overrides always win over rules, and re-running rules over the whole
history is idempotent.

### `import_mappings`
Per-account CSV column mapping and sign convention, persisted so a recurring import from the
same institution is one click.

### `card_perks` + `perk_redemptions`
A recurring benefit on a credit card, and one row per period it was used in. A perk stores
`anchor_on` — the date its first period began — and every period is that date stepped by its
cadence, so a calendar-year credit and one that resets on the cardmember anniversary are the
same arithmetic. `period_start` is stored on the redemption rather than recomputed, because it
is the fact being recorded. Ticket 049.

## Endpoints

The route inventory — with the ticket that landed each route — is the table in
[design-docs/api-contract.md#endpoints](design-docs/api-contract.md#endpoints), which
`api/tests/test_contract.py` checks against the running app. Parameters and shapes are
generated into [generated/api-endpoints.md](generated/api-endpoints.md).

## Account sources

Every account carries a `source`. v1 ships `manual` and `csv` only.

This is deliberate and it is the single most important sequencing decision in the project.
Institution aggregation is the part of this app we have the *least* control over:

- Plaid's free trial caps at ~10 live Items.
- Teller's free tier is generous but covers no investment accounts.
- SimpleFIN is ~$15/yr, read-only, daily refresh.
- Fidelity has actively blocked aggregator access; Fidelity, Schwab, and JPMorgan have
  pushed aggregators into paid data deals. **401k and HSA are the worst-covered account
  categories in the entire ecosystem** — and they're a large share of the net worth here.
- CFPB's Section 1033 open banking rule was finalized Oct 2024, **enjoined** Oct 2025, and is
  mid-rewrite with "may data providers charge fees?" reopened.

Manual + CSV covers 100% of institutions including the ones no aggregator handles, works on
day one, and proves the entire application. Connectors then become strictly additive tickets
behind a `SourceAdapter` interface: `fetch_accounts()`, `fetch_balances()`, `fetch_transactions()`.

Build the interface in v1. Implement only `manual` and `csv` behind it.

## Hosting

**Neon** for Postgres, **Fly.io** for both services, **Cloudflare** for DNS, TLS, and Access.

Neon over a self-operated Fly Postgres VM for one reason: [SECURITY.md](SECURITY.md#backups)
argues that moving a financial picture out of Google Sheets into a self-run database is a
durability downgrade until backups are proven. Operating a single-node Postgres myself
maximises exactly that downgrade. Neon's automatic backups and PITR, *plus* the nightly
`pg_dump` in ticket 017, give two independent layers for $0 on the free tier.

Practical notes:

- Use Neon's **pooled** connection endpoint; configure the SQLAlchemy pool accordingly.
  Serverless Postgres plus a long-lived connection pool has sharp edges.
- Neon autosuspends on idle. First request after a suspend pays a cold start.
- Real and demo are **separate Neon projects**, not two branches of one. Branches share a
  project and an account; that is a weaker boundary than the separate-credentials guarantee
  ticket 037 exists to provide. Branching is the right tool for dev/prod convenience and the
  wrong one for a public-facing trust boundary.
- Free-tier allowances are **per project**: 0.5 GB storage, 100 CU-hours/month, 5 GB egress,
  10 branches. Two projects on the free plan covers this app. Storage and egress are not
  close to binding — a household's finance data is tens of megabytes.
- **Compute hours are the one limit worth watching, and only on the demo.** At minimum
  sizing that budget is roughly 400 wall-clock hours of awake compute per month against a
  ~730-hour month. The real app, used by one household with a 5-minute autosuspend, will not
  come near it. The public demo can: it is indexed by design, and a crawler hitting it
  regularly keeps the database permanently awake.

  The fix is the same thing that makes the demo good — see [demo caching](#demo-caching).
- Use a **branch of the real project** as the scratch target for ticket 017's tested restore.
  That is exactly what branches are for, and it costs nothing.

### Demo caching

The demo is read-only over a static synthetic dataset, which means nearly every response can
be cached at the edge with a long TTL. Doing so buys three things at once:

1. **Keeps demo compute inside the free tier** — crawlers and repeat visitors are served by
   Cloudflare and never wake Neon.
2. **Removes the cold start on a first visit.** Neon autosuspends after 5 minutes idle and
   Fly machines auto-stop, so an uncached click on a fully idle demo pays both. A public
   link that takes several seconds to render a blank page is a broken link as far as whoever
   clicked it is concerned. A cached page is instant.
3. Costs nothing and needs no extra infrastructure.

Cache at the Cloudflare layer on the demo hostname only. The real app must never be cached
at the edge — it is behind Access and its responses are personal.
- Fly machines run `auto_stop_machines` so idle cost stays near zero.
- Migrations run as a Fly **release command**, not on boot — two booting instances would
  race the same migration.

Running cost: roughly $0–10/month plus a domain. See ticket 008.

## Why not Kubernetes

The learning goal explicitly includes containers and orchestration, so this needs a real answer.

K8s for a single-household app is the wrong tool by roughly two orders of magnitude. It would
consume weeks that v1 needs, and the operational complexity it adds buys nothing at one
household of traffic — there is no scaling event to absorb, no rolling deploy worth
orchestrating, no bin-packing problem to solve.

The sequencing that serves both goals:

- **Now:** Docker + Fly.io + managed Postgres. You still write Dockerfiles and handle
  migrations, secrets, health checks, private networking, and release commands. Real, not a sink.
- **Later, optional, after the app works:** redeploy the same app to k3s on a VPS purely as
  a learning exercise. The written retro of what it cost versus what it bought is a better
  artifact than the cluster itself.

The things that will actually teach the most about databases live in the app, not the infra:
hand-reviewed migrations, the effective-dated ownership model, and the snapshot history.

## Operations

- **Logs:** structlog, JSON, with request id, method, path, status, duration. **Financial
  values are never logged** — there is a redaction filter and a test asserting it works.
  Structured logs are useless if reading them means reading your own balances out of a log
  aggregator.
- **Errors:** Sentry on both services, DSN from env, disabled when unset.
- **Liveness vs readiness:** `/health` reports process liveness and touches no database.
  `/ready` reports database reachability. Fly probes `/health` only — probing `/ready` would
  let a transient database blip restart otherwise-healthy instances.
- **Backups:** Neon's own point-in-time recovery, plus `make backup` writing a full JSON
  export to the owner's machine. Nothing we operate holds an offsite copy — see
  [ADR 0008](adr/0008-local-backups.md). A silently-failing scheduled backup is worse than
  no backup because it is trusted, which is why there is no schedule.

## Testing

Every ticket ships both unit and functional tests. See [PLANS.md](PLANS.md#tests).

- **Backend unit:** pure service functions. Every aggregate (net worth, runway, spend
  rollups) gets a test with hand-computed expected values. Ownership math gets property
  tests — stakes summing over 100%, stakes changing mid-history, rounding at the half-cent.
- **Backend functional:** httpx against the app with a real test database, migrated with
  `alembic upgrade head`. Tests never use `metadata.create_all()` — if they did, tests and
  production would drift and broken migrations would ship green.
- **Frontend unit:** vitest for formatters, hooks, and query builders.
- **Frontend functional:** Testing Library against MSW mocks typed from `api-types.ts`.
- **E2E:** two Playwright smoke tests — the dashboard against the synthetic seed, and the
  CSV import wizard end to end.
- **Coverage is reported in CI but not gated on a percentage.** Coverage gates get satisfied
  by tests that assert nothing.
- **Fixtures are always synthetic.** No test ever contains a real balance.
