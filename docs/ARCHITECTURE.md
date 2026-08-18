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
                                             │  Fly private network (.flycast)
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
| auth | Cloudflare Access + passkey | none (public) |
| database | real Neon project | **separate Neon project**, synthetic seed |
| writes | yes | rejected at the API layer |
| indexing | `noindex` | indexed |

The demo deployment holds credentials that cannot reach the real database. This is the
security boundary — not a feature flag. See [SECURITY.md](SECURITY.md#demo-isolation).

## Request path

**The browser only ever talks to `<domain>`.** Next.js route handlers under `/api/*`
proxy to the FastAPI service over Fly's private network. The API has no public address at
all.

This is a deliberate choice with four consequences, all of them the reason for it:

1. **Origin lock is structural.** There is no public API hostname to leave unprotected. A Fly
   app is publicly addressable by default; putting Cloudflare Access in front of a
   reachable origin is a false sense of security. Here there is nothing to reach.
2. **No CORS, anywhere.** Same origin. The API ships no CORS middleware, and CI fails if
   `NEXT_PUBLIC_API_URL` or an absolute API origin appears in `web/`.
3. **One Cloudflare Access application, not two.** Access answers unauthenticated requests
   with a redirect to the identity provider. A `fetch()` cannot meaningfully follow that —
   an expired session would surface as an opaque network failure instead of a `401`. With
   the API behind the BFF, only page navigations ever hit Access, which is exactly what
   Access is designed for.
4. **Sessions are simple.** One origin means one cookie scope and no cross-site negotiation.

What it costs: a thin proxy route handler, and server-side code has to know the internal API
URL while the browser knows no API URL at all. That split has to be right from ticket 002 —
locally the API is `http://api:8000`, in production it's the `.flycast` address.

The two-service split itself is unchanged: two Dockerfiles, two deploys, two ecosystems.

## The API contract

The decision was to not hand-write or maintain an OpenAPI spec. We don't. FastAPI *emits*
`openapi.json` from the Pydantic models we write anyway, and the frontend generates
TypeScript types from it:

```
Pydantic response models  →  openapi.json  →  openapi-typescript  →  web/src/lib/api-types.ts
        (source of truth)      (generated)        (generated, committed)
```

`make types` runs the pipeline. CI regenerates and fails on diff.

Why this matters more here than usual: tickets are implemented across sessions with no shared
memory, and in Wave 2 they run **in three parallel lanes**. Without a frozen contract, a
frontend session writes a component against a response shape a backend session never built,
and nothing catches it until runtime. Ticket 012 declares every model and every route up
front — stubbed at `501` — so the contract exists before any implementation does. After that,
drift is a failed CI check rather than a merge conflict.

**The Pydantic models are the contract.** The frontend never hand-writes an API response type.

## Users and ownership

### `users`

```
id, email, display_name, is_active
```

v1 ships with one row. The second row is a partner: insert it, add the identity to the
Cloudflare Access policy, register a passkey. No invitations, no roles, no sharing UI.

The `users` table is also the auth allowlist — there is no separate allowlist config.

### ★ `ownership_stakes`

The requirement: *if I own 50% of an asset, only 50% counts toward my net worth.* Same for
liabilities.

```
account_id, owner_user_id → users.id, percentage, effective_from, effective_to (nullable)
```

**Every account gets an explicit 100% stake row when it is created.** There is no implicit
"an account with no stake row is fully owned" default — with two possible owners that default
is ambiguous, and removing it deletes a special case from the lookup helper rather than
adding one.

**Effective-dated.** A stake that changes on 2027-03-01 closes the old row and opens a new
one. Without this, changing a stake silently rewrites your historical net worth — the charts
would retroactively lie. This costs almost nothing now and cannot be added cheaply later.

Invariant, enforced in code and by test: for any account, stakes overlapping any given date
sum to ≤ 100%.

### Visibility: household-shared

Both users see every account. Only the *money* splits:

- `net_worth(as_of, viewer_id)` returns that user's ownership-adjusted share.
- `net_worth(as_of, viewer_id=None)` returns the household total across all stakes.
- The dashboard has a **Mine / Household** toggle. That is the entire multi-user surface.

Per-account privacy was rejected: it means filtering every query by viewer, which is a
multi-tenancy tax on an app that will never have tenants.

**Spend and runway are per-account and are never fractionally attributed by ownership.** A
$60 grocery charge on a jointly-owned card is $60 of spend, not $30. Splitting spend by
ownership stake is a rabbit hole with no correct answer, and it isn't what the number is for.

### Ownership is applied in exactly one place

**Every** net worth figure is ownership-adjusted. There is no code path that sums raw
balances. The adjustment — and the rounding it implies — happens in a single helper in
`api/app/services/ownership.py`, and everything calls it. If you find yourself writing
`SUM(balance)`, stop.

## Money

`Decimal` in Python, `NUMERIC(19,2)` in Postgres, **integer cents** over the wire. Never
float, anywhere, for any reason. There is a CI check that fails if `Float` appears in a
SQLAlchemy column definition.

Two decimal places everywhere is deliberate. Balances are dollars-and-cents; the extra
precision would be spurious for a number that changes daily anyway, and 2dp storage
round-trips exactly through integer cents, so the wire format needs no scale field and no
decimal strings.

### Rounding

Ownership math produces fractional cents — 50% of $1,234.57 is $617.285. The rule:

> **Round half-up, per account, immediately after applying the stake. Then sum.**

Rounding per account rather than on the total means the figure on screen always equals the
sum of the rows above it. Rounding at the end produces a dashboard where the numbers visibly
don't add up, which destroys trust in every other number on the page.

This is the only rounding site in the codebase.

If holdings-level tracking (shares × price) is ever added, prices need their own precision —
2dp is correct for balances and wrong for unit prices. That's a Later concern, called out so
nobody assumes 2dp generalises.

## Data model

Eleven tables, all created in **one hand-reviewed migration** (ticket 009). The two marked ★
are load-bearing — they are the reason this app is not a spreadsheet, and getting them wrong
means rewriting every aggregate query later.

One upfront migration is a deliberate trade. Alembic's revision chain is linear, so parallel
branches each adding a migration produce a branched head that has to be merged by hand. A
single v1 schema removes that from the critical path entirely and is what makes Wave 2's
three lanes safe. Post-v1 schema changes are incremental and serialised through one lane.

### `institutions`
Banks, brokerages, lenders, 401k and HSA providers. Mostly a display grouping.

### `accounts`
Every asset and liability. Key columns:

- `kind` — `liquid_asset | illiquid_asset | liability`
- `subtype` — `checking | savings | brokerage | 401k | hsa | real_estate | credit_card | mortgage | auto_loan | ...`
- `source` — `manual | csv | teller | plaid | simplefin` ← see [Account sources](#account-sources)
- `currency` — `CHECK (currency = 'USD')` in v1. Stored so the constraint can be relaxed later.
- `closed_at` — nullable. See [Closed accounts](#closed-accounts-and-carry-forward).

Liabilities are stored as **positive** balances with `kind = liability`. Net worth subtracts
them. Do not store negative balances to represent debt — it makes every aggregate ambiguous.

### ★ `balance_snapshots`
```
account_id, as_of (date), balance, source     -- unique (account_id, as_of)
```

Aggregators return *current* balances; essentially nobody backfills years of history.
Which means: **history that isn't captured is lost permanently.** Snapshots start on first
deploy and every balance write appends one.

"Net worth over time" is a derived view over this table. It is not computable any other way.
The Google Sheet import exists to seed this table with the history that predates the app.

Current balance is **derived** as the latest snapshot, never duplicated onto `accounts`. That
removes a whole class of consistency bug; accept the join.

### Closed accounts and carry-forward

You will not snapshot every account every day, so a net worth series has to carry the last
known balance forward. Carry-forward without a close date is a correctness bug: sell the car,
stop updating the account, and its final balance sits in your net worth forever. Same for a
paid-off loan or a rolled-over 401k.

Two mechanisms, both required:

- **`closed_at`** — an account is excluded from any `as_of` at or after its close date.
- **A 3-month staleness cap** — a snapshot carries forward at most 3 months. Past that the
  account still counts, but the value is flagged stale in the API response and surfaced in
  the UI as a prompt to update it.

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

### `credentials`
WebAuthn public keys and sign counts, FK to `users`.

### `data_marker`
A single row recording whether this database holds real or synthetic data. The synthetic seed
script refuses to run against a database marked real.

## Endpoints

The complete v1 surface. Declared by ticket 012 and stubbed at `501` until the named
ticket implements it.

**This table is checked against the running app by a test.** Adding a route without
listing it here, or listing one that does not exist, fails the suite — a stale
inventory is worse than none, because it is trusted.

| Method | Path | Ticket |
|---|---|---|
| GET | `/health` | 003 |
| GET | `/ready` | 003 |
| GET | `/net-worth` | 014 |
| GET | `/net-worth/series` | 014 |
| GET | `/spend` | 015 |
| GET | `/runway` | 016 |
| GET | `/export` | 017 |
| GET POST | `/accounts` | 019 |
| GET PATCH | `/accounts/{account_id}` | 019 |
| GET | `/accounts/{account_id}/history` | 019 |
| POST | `/accounts/{account_id}/balances` | 019 |
| POST | `/accounts/{account_id}/stakes` | 019 |
| POST | `/import/csv/preview` | 020 |
| POST | `/import/csv/commit` | 021 |
| GET POST | `/rules` | 022 |
| PATCH DELETE | `/rules/{rule_id}` | 022 |
| POST | `/rules/apply` | 022 |
| GET | `/transactions` | 023 |
| PATCH | `/transactions/{transaction_id}` | 023 |
| POST | `/transactions/bulk-categorise` | 023 |
| POST | `/auth/register/options` | 034 |
| POST | `/auth/register/verify` | 034 |
| POST | `/auth/login/options` | 034 |
| POST | `/auth/login/verify` | 034 |
| GET | `/auth/session` | 034 |

Query parameters, request bodies, and response shapes are defined in
`api/app/schemas/` and generated into `web/src/lib/api-types.ts`. They are deliberately
not duplicated here — a hand-maintained copy would go stale, which is the whole reason
the contract is generated.

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
- **Backups:** nightly encrypted `pg_dump` to Cloudflare R2, 30-day retention, with a
  dead-man's-switch that alerts when the job *doesn't* check in. A silently-failing backup is
  worse than no backup, because it is trusted.

## Testing

Every ticket ships both unit and functional tests. See [tickets/README.md](../tickets/README.md#tests).

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
