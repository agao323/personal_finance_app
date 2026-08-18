# Decisions

Append-only. Newest first. Each entry: what was decided, why, and what it rules out.
Implementation-level decisions made during tickets go in `adr/` instead.

---

## 2026-08-14 — Plan review: six corrections before implementation

A review of the initial plan surfaced gaps that would have surfaced mid-ticket as rework.
All six are settled here. Two of them supersede decisions in the entries below.

### Household, not single user — `users` table ships in v1

**A `users` table and `ownership_stakes.owner_user_id` exist from the first migration. v1
ships with one row.** Visibility is household-shared: both users see every account, and only
the money splits, via `net_worth(as_of, viewer_id)`. A **Mine / Household** toggle is the
entire multi-user product surface.

*Why:* the original plan had `ownership_stakes.owner` with no definition of which owner's
stake counted toward net worth — a hole in the load-bearing calculation. Resolving it
requires deciding whether there is more than one owner, and the answer is yes, later.
Building it now is +1 ticket. Retrofitting it means changing every service signature, every
endpoint, a data migration to backfill user ids, and reworking the auth allowlist — 4–6
tickets, performed while the app holds real data.

Adding it also *removes* a special case: every account now gets an explicit 100% stake row at
creation, so the lookup helper has no implicit-default branch.

*Rules out:* per-account privacy, invitations, roles, a permissions UI. Not multi-tenancy —
two users is a household, and the anti-scale position in PRODUCT.md is unchanged.

*Supersedes:* "One user. Ever." in PRODUCT.md, now "One household. Two users, maximum, ever."

### The browser never calls the API directly — Next.js is a BFF

**All browser traffic goes to `<domain>`. Next.js route handlers under `/api/*` proxy to
FastAPI over Fly's private network. The API has no public address.**

*Why:* the original plan configured CORS for a browser-to-API call, which forces three
problems that all disappear together. Cloudflare Access answers unauthenticated requests with
an IdP redirect, which `fetch()` cannot follow — every session expiry would surface as an
opaque network error instead of a `401`. "Origin rejects requests that did not pass through
Access" needed a mechanism nobody had picked, on an app that Fly makes publicly addressable
by default. And two hostnames means two Access applications to keep in sync.

With the BFF: origin lock is structural rather than configured, CORS disappears, there is one
Access application, and sessions are single-origin.

*Cost, accepted:* a proxy route handler, and a strict split between the browser (which knows
no API URL) and server-side code (which knows the internal one).

*Rules out:* `NEXT_PUBLIC_API_URL`, CORS middleware, a publicly addressable API. CI enforces
the first two.

### Money is 2 decimal places, and rounding happens once

**`NUMERIC(19,2)` in Postgres, `Decimal` in Python, integer cents over the wire. Round
half-up, per account, immediately after applying the ownership stake, then sum.**

*Why:* the original plan specified `NUMERIC(19,4)` storage with integer-minor-unit wire
format, which does not round-trip — `1234.5678` becomes `123457` cents and back to
`1234.5700`. Balances are dollars and cents and change daily; the extra precision was
spurious. Dropping to 2dp makes integer cents exact and needs no scale field or decimal
strings.

Rounding per account rather than on the total means the displayed figure always equals the
sum of the rows above it. Rounding at the end produces a dashboard whose numbers visibly
don't add up, which discredits every other number on the page.

*Rules out:* holdings-level tracking (shares × price) without a second precision regime.
Recorded in PRODUCT.md as Later.

### Burn is gross spend; transfers and closed accounts are modelled explicitly

**Burn = gross spend excluding transfers. Income is classified but not netted and not
displayed in v1.** Runway answers "how long if income stopped," which is the only version
worth a tile while income is coming in.

Three schema additions the original plan assumed but never created:

- `categories.kind` (`income | expense | transfer`) — spend rollups filter to `expense`.
  Ticket 018's "excludes transfers" had no mechanism behind it.
- `transactions.transfer_group_id` — links matched pairs, set by hand in v1.
- `accounts.closed_at` plus a 3-month carry-forward staleness cap. Carry-forward is required
  for a net worth series, and carry-forward without a close date leaves a sold car in your
  net worth forever.

Also settled: **outflows are negative**, with a per-mapping sign-normalisation step in CSV
import, because institutions disagree.

*Rules out:* net burn and income views in v1; automatic transfer-pair detection in v1.

### Neon, not a self-operated Postgres

**Neon for both databases, separate projects for real and demo.**

*Why:* SECURITY.md argues that moving out of Google Sheets into a self-run database is a
durability downgrade until backups are proven. Operating a single-node Postgres VM maximises
exactly that downgrade. Neon's automatic backups and PITR plus the nightly `pg_dump` in
ticket 017 give two independent layers, on the free tier, for $0.

Separate Neon *projects* rather than branches: branches share a project and account, which is
weaker than the separate-credentials boundary the demo isolation depends on.

Confirmed against Neon's 2026 free plan: up to 100 projects, with 0.5 GB storage, 100
CU-hours, 5 GB egress and 10 branches **per project**. Two free projects covers this app with
room to spare, so the separation costs nothing.

The one live constraint is demo compute: a publicly indexed demo that crawlers keep awake can
burn its CU-hour budget. Handled by edge-caching the demo at Cloudflare, which also removes
the cold start an uncached first visit would otherwise pay — see
[ARCHITECTURE.md](ARCHITECTURE.md#demo-caching) and ticket 037.

*Rules out:* Fly Postgres. Also rules out using two **branches** of one Neon project for
real and demo, which is the conventional advice for dev/prod and the wrong answer here —
branches share a project and an account, and this is a trust boundary rather than an
environment split.

### Five capabilities the plan assumed but never built

Added as tickets: **manual category override** (API + UI — `category_source='manual'` was
designed for but nothing ever wrote it), **a transactions screen** (in the nav, no ticket),
**a rules management screen** (PRODUCT.md commits to a user-editable rule set; editable by
curl is not that), **observability** (structlog + Sentry + log redaction), and **backup
failure alerting**.

---

## 2026-08-14 — Waves and lanes: contract-first parallelism

**Wave 0 foundations and Wave 1 schema/contract are serial. Wave 2 runs in three parallel
lanes. Wave 3 auth and ship is serial.** Full structure in `tickets/README.md`.

*Why:* the binding constraint on parallel agent work is interface contracts and the linear
Alembic revision chain — not prompt quality. Both are removable up front:

- **One hand-reviewed migration creates the entire v1 schema** (ticket 009). Alembic's chain
  cannot absorb concurrent branches; a single v1 schema takes migrations off the critical
  path. Post-v1 changes are incremental and serialised through one lane.
- **Every Pydantic model and every route is declared and stubbed at `501` before any
  implementation** (ticket 012), and `api-types.ts` is generated from it. Frontend and backend
  are then typed against the same frozen file and cannot drift, whichever lands first.

Lanes own disjoint file sets. Only tickets 012 and Wave 4 may edit `api-types.ts`; a Wave 2
ticket needing a response-shape change stops and re-freezes rather than editing it.

*Cost, accepted:* one large initial migration reads as less incremental than a granular
history, and three concurrent lanes consume review bandwidth. Lane C (frontend) is the
critical path at nine tickets; if a fourth lane is ever wanted, split it after the app shell
lands.

*Supersedes:* "Rules out: parallel agents on the shared codebase" in the entry below. That
ruling was about interface drift, which ticket 012 eliminates.

**Deploy moves from ticket 029 to ticket 008.** A skeleton — `/health` and an empty page —
goes live on a real domain with TLS, Neon, and release-command migrations before any feature
exists.

*Why:* every unknown in "deploy it into a live environment" was concentrated at the end of the
plan. Surfacing Fly private networking, Neon pooling, release commands, TLS, and secrets on an
empty app costs a day; discovering them on a finished app is the classic 90%-done month.

**Ticket 016 (Google Sheet history import) rebased off the rules engine.** It seeds
`balance_snapshots` and only needs the snapshot service; it was gated behind CSV import and
transaction categorisation, which concern a different table.

---

## 2026-08-14 — Backend/frontend split, contract via generated types

**Next.js + TypeScript frontend, separate FastAPI + Python backend.** Two top-level
directories, two Dockerfiles, two deploy targets.

*Why:* mirrors a real production architecture, which is the shape the learning goal is aimed
at — two services, two deploy targets, a contract between them, private networking. Python is
also where the financial modelling that's coming — FIRE projections, sequence-of-returns
sensitivity, Monte Carlo over withdrawal rates — is materially easier than it would be in
TypeScript. Note honestly that this second argument is about features currently in *Later*,
not v1; the learning and separation-of-concerns arguments carry the decision on their own.

*Cost, accepted:* roughly 4–6 extra tickets of infrastructure (two Dockerfiles, two test
setups, two dependency ecosystems, a codegen step, a proxy layer), and the loss of free
end-to-end type inference.

*Rules out:* a single Next.js app with server actions; tRPC.

**API contract: FastAPI-generated OpenAPI → generated TypeScript types. No hand-written spec.**

*Why:* the original plan called for a hand-maintained OpenAPI spec, which was rejected — a
YAML file nobody reads goes stale. But dropping the *contract* entirely breaks multi-session
ticketing: a later session writes a component against a response shape an earlier session
never built, and nothing catches it. FastAPI resolves this for free — it emits `openapi.json`
from the Pydantic models that have to exist anyway, and `openapi-typescript` turns that into
frontend types. Nothing is hand-maintained; drift becomes a failed CI check.

*Rules out:* hand-written OpenAPI YAML; hand-written frontend response types.

**Schema designed now, reconciled against the Google Sheet during the import ticket.**

*Why:* the structurally risky parts — effective-dated ownership, snapshot history,
idempotent transaction ingestion — are generic and don't depend on anyone's spreadsheet
layout. What the sheet actually determines is the *category taxonomy* and account naming,
which are data, not schema. So the migration risk of deciding now is low and concentrated
in seed data rather than table structure.

---

## 2026-08-14 — Foundational four

**V1 scope: manual + CSV core, no connectors.**
Schema → Google Sheet history import → CSV/manual entry → dashboard (ownership-adjusted net
worth, runway/burn, net worth over time, spend by category) → auth + separate demo deploy →
deployed with migrations, backups, CI.

*Why:* aggregation is the least controllable part of the project — Plaid's ~10-item free
trial cap, Teller's lack of investment accounts, Fidelity actively restricting aggregators,
CFPB 1033 enjoined and mid-rewrite. Manual/CSV covers 100% of institutions including 401k
and HSA, and proves the whole app with zero external blockers.

*Rules out:* any connector as a v1 dependency. Every account carries a `source` field so
connectors are strictly additive behind a `SourceAdapter` interface.

**Infra: Docker + Fly.io + managed Postgres.**

*Why:* keeps real infra learning — Dockerfile, migrations, secrets, health checks, private
networking — without the time sink.

*Rules out:* Kubernetes in the initial build. k3s stays an explicit optional Phase 2
side-quest *after* the app works, with a written cost/benefit retro as the deliverable.

**Auth: Cloudflare Access on the real app + passkey auth implemented in code.**

*Why:* edge-enforced identity protects real data with zero auth code in the request path;
the passkey implementation lives in the codebase and is exercised by production and its test
suite, preserving the learning value without putting real money behind hand-rolled auth.

*Rules out:* password auth entirely.

**Workflow: ticketed sessions, contracts first.**
Lock schema and API contract before implementation tickets. Small tickets — one migration +
one endpoint + one component + tests; split anything touching more than ~5 files. Every
ticket ends in a green test run and a commit.

*Why:* repo state — ticket files with status and acceptance criteria — is what makes sessions
resumable across usage limits. The agent cannot reliably introspect its own quota, so
resumability has to live on disk.

*Rules out:* meta-prompting / LLM-grades-the-plan loops as a planning step.
