# Architecture

The map of the system: its shape, how a request travels, the layers and which files own
each domain, and the invariants — each linking to the design doc that argues it and the
check that enforces it. Rationale lives in [design-docs/](design-docs/index.md); columns and
routes are generated into [generated/](generated/db-schema.md). **If this file and the code
disagree, the code wins** — fix this file in the same commit.

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
application. [design-docs/request-path.md](design-docs/request-path.md).

## The API contract

**The Pydantic models are the contract.** `openapi.json` is emitted from them and
`web/src/lib/api-types.ts` is generated from that; `make types-check` fails on drift.
[design-docs/api-contract.md](design-docs/api-contract.md).

## Layers

### API — `api/app/`

```
models ──► schemas ──► services ──► routers ──► main.py
```

| Layer | Holds | Must not import |
|---|---|---|
| `models/` | SQLAlchemy tables and enums; sees only `db.Base` | services, schemas, routers |
| `schemas/` | Pydantic request/response models — the contract; may use `models.enums` | services, routers |
| `services/` | Domain logic and queries: ownership, rounding, balances, periods | routers, `fastapi` |
| `routers/` | HTTP: validate, call services, shape the response | other routers |
| `main.py` | Wires routers, middleware, logging, Sentry | — |

Cross-cutting concerns enter at the edges. Routers get the session and the identity only
through `deps.py` (`DbSession`, `CurrentUser`), which is where `config`, `db` and
`services/access.py` meet. `main.py` installs `middleware.py` (request context, demo
read-only), `logging.py` and `observability.py`. As the code actually is: eight of twelve
routers still build SQL themselves rather than calling a service — allowlisted as debt
(TD-001), and new queries go in services. Enforced by `api/tests/test_architecture.py`,
whose allowlist may only shrink.

### Web — `web/src/`

```
lib/api-types.ts ──► lib/api.ts ──► components/ ──► app/ (routes)
```

`app/api/[...path]/route.ts` is the only code that knows the API URL; `lib/api.ts` is the
only fetcher; `api-types.ts` is generated and imported as types only; `proxy.ts` is Next
16's middleware and verifies Access. Enforced by `web/eslint.config.mjs` and
`scripts/check_no_public_api_url.sh`. [FRONTEND.md](FRONTEND.md).

## Domain map

API paths are under `api/app/`, tests under `api/tests/`, web under `web/src/`. Specs:
[product-specs/](product-specs/index.md).

| Domain | API: models · schemas · services · routers | Web: routes · components | Tests |
|---|---|---|---|
| Net worth | `account` · `net_worth` · `net_worth`, `ownership`, `balances` · `net_worth` | `/` · `tiles/net-worth`, `charts/net-worth-chart`, `view-toggle` | `test_net_worth`, `test_net_worth_series`, `test_api_net_worth`, `test_ownership`; `charts/net-worth-chart.test` |
| Runway | — · `runway` · `runway`, `spend`, `ownership` · `runway` | `/` · `tiles/runway` | `test_runway`; `(dashboard)/page.test` |
| Spending | `transaction` · `spend` · `spend` · `spend` | `/spending` · `charts/category-breakdown`, `period-selector`, `transaction-table` | `test_api_spend`; `spending/page.test`, `category-breakdown.test` |
| Accounts & stakes | `account` · `account` · `accounts`, `ownership`, `balances` · `accounts` | `/accounts`, `/accounts/[id]`, `/accounts/new` · `account-row`, `forms/*` | `test_api_accounts`, `test_ownership`, `test_balances`; `accounts/**/page.test`, `forms.test` |
| Transactions & rules | `transaction` · `transaction`, `rule` · `categorize` · `transactions`, `rules`, `categories` | `/transactions`, `/rules` · `transaction-*`, `category-picker`, `rules/*` | `test_api_transactions`, `test_categorize`, `test_api_categories`; `transactions/`, `rules/` page tests |
| CSV import | `system` (`ImportMapping`) · `import_csv` · `csv_import`, `balances` · `import_csv` | `/import` · `import/*` | `test_csv_import`; `import/page.test` |
| Sheet import | script `api/scripts/import_sheet_history.py` + `api/config/sheet_mapping.example.toml` | — | `test_sheet_import` |
| Cards & perks | `card_perk`, `account` · `card_perk` · `perks` · `cards` | `/cards`, `/cards/[id]` · `cards/*` | `test_perks`, `test_cards`; `components/cards/*.test`, `cards/*.test` |
| Export & backup | — · `export` · — · `export`; scripts `export_local.py`, `restore_local.py` | — | `test_export` |
| Household & auth | `user` · `user`, `auth` · `access` · `users`, `auth`; `deps.py` | `/settings/household` · `account-menu`; `lib/access.ts`, `proxy.ts` | `test_auth`, `test_deps_access_auth`; `household/page.test`, `proxy.test` |
| Demo | `config.py`, `middleware.py` | `demo-banner`, `lib/demo.ts` | `test_demo_mode`; `demo-banner.test`; `scripts/check_demo_isolation.sh` |
| Platform | `main.py`, `config.py`, `db.py`, `logging.py`, `observability.py`, `serve.py` | `app/api/[...path]`, `healthz`, `lib/api.ts`, `lib/sentry.ts`, `nav` | `test_health`, `test_db`, `test_config`, `test_logging`, `test_contract`, `test_schema`; `api.test`, `route.test` |

## Invariants

| Invariant | Enforced by | Design doc |
|---|---|---|
| <a id="users-and-ownership"></a>**Users and ownership.** Every net worth figure is ownership-adjusted. Stakes are effective-dated and half-open, sum to ≤ 100% on any date, and every account has an explicit 100% row — no implicit default. Both users see everything; only money splits (Mine / Household). Spend and burn are never split | `test_ownership`, `ck_stakes_*` | [ownership-and-rounding](design-docs/ownership-and-rounding.md) |
| <a id="ownership-is-applied-in-exactly-one-place"></a>**Ownership is applied in exactly one place:** `services/ownership.adjust()`. No net worth figure comes from raw balances | `test_architecture`, `test_net_worth_series` | [ownership-and-rounding](design-docs/ownership-and-rounding.md#ownership-is-applied-in-exactly-one-place) |
| <a id="money"></a>**Money** is `Decimal` / `NUMERIC(19,2)` / integer cents on the wire. Never float | `check_no_float.sh`, `test_contract` | [ownership-and-rounding](design-docs/ownership-and-rounding.md#money) |
| <a id="rounding"></a>**Rounding:** half-up, per account, right after applying the stake, then sum | `test_ownership` | [ownership-and-rounding](design-docs/ownership-and-rounding.md#rounding) |
| <a id="accounts"></a>**Liabilities are stored positive**; current balance is derived, never stored | `test_balances` | [data-model](design-docs/data-model.md#accounts) |
| <a id="closed-accounts-and-carry-forward"></a>**Every balance write appends a snapshot.** Carry-forward is capped at 90 days (flagged, not dropped); `closed_at` stops an account counting | `test_balances`, `test_net_worth` | [snapshots-and-carry-forward](design-docs/snapshots-and-carry-forward.md) |
| <a id="transactions"></a>**Ingestion is upsert, never insert**, keyed on `external_id` + an occurrence index | `test_csv_import` | [transactions-and-ingestion](design-docs/transactions-and-ingestion.md) |
| <a id="transfers"></a>**Transfers and income never count as spend** (`categories.kind`) | `test_api_spend` | [transfers-and-categories](design-docs/transfers-and-categories.md) |
| <a id="categories--categorization_rules"></a>**Rules never overwrite a manual category**; first match wins; re-running is idempotent | `test_categorize`, `test_api_transactions` | [transfers-and-categories](design-docs/transfers-and-categories.md#categories-and-rules) |
| <a id="card_perks--perk_redemptions"></a>**`services/perks.py` alone decides which period a date is in**; `period_start` is stored; nothing reads the clock | `test_perks`, `test_cards` | [card-perks-period-engine](design-docs/card-perks-period-engine.md) |
| The request is the transaction boundary: endpoints flush, `get_session` commits | `test_db` | [ADR 0005](adr/0005-request-scoped-transactions.md) |

The full list of golden principles, with what enforces each, is
[design-docs/core-beliefs.md](design-docs/core-beliefs.md).

## Everything else

| Topic | In one line | Where |
|---|---|---|
| <a id="data-model"></a>Data model | Twelve tables; the v1 eleven came from one reviewed migration so Wave 2's lanes could not collide | [data-model](design-docs/data-model.md), [db-schema](generated/db-schema.md) |
| <a id="endpoints"></a>Endpoints | Every route with the ticket that landed it, checked against the app by `test_contract.py` | [api-contract#endpoints](design-docs/api-contract.md#endpoints), [api-endpoints](generated/api-endpoints.md) |
| <a id="account-sources"></a>Account sources | `manual` and `csv` only, deliberately; SimpleFIN is planned | [account-sources](design-docs/account-sources.md) |
| <a id="hosting"></a>Hosting | Neon (pooled; separate projects for real and demo), Fly (API on `.internal` only), Cloudflare | [hosting](design-docs/hosting.md) |
| <a id="operations"></a>Operations | `/health` vs `/ready`, logs without values, Sentry, backups, booting the app | [RELIABILITY.md](RELIABILITY.md) |
| <a id="testing"></a>Testing | Unit + functional per plan, real migrated Postgres, coverage reported not gated | [PLANS.md#tests](PLANS.md#tests), [QUALITY_SCORE.md](QUALITY_SCORE.md) |
