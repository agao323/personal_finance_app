# AGENTS.md

A personal finance web app for one household (Allen, plus a partner later): net worth,
spending, runway and card credits, with fractional, effective-dated ownership. FastAPI and
Postgres behind a Next.js BFF, on Fly.io, Neon and Cloudflare Access. This file is the
map — every doc is at most two links from here. Keep it under 100 lines; a check enforces it.

## Session workflow

Follow [docs/PLANS.md](docs/PLANS.md). In short:

1. Take the lowest-numbered `Status: todo` plan in `docs/exec-plans/active/` **in your
   lane** ([index](docs/generated/exec-plans.md)). Check its **Blocked by**.
2. Read the plan, then only the docs its **Read first** lists.
3. Implement exactly its scope. Adjacent work becomes a new plan or a
   [tech-debt](docs/exec-plans/tech-debt-tracker.md) item — never scope creep.
4. `make lint && make test && make types-check`, all green.
5. Commit `<id>: <imperative summary>`. Set `Status: done`, `git mv` it to `completed/`,
   run `make docs`, commit.

## Where to look

| Question | Read |
|---|---|
| What is this? What is out of scope, Later, Rejected? | [PRODUCT.md](docs/PRODUCT.md) |
| What does a feature do — rules, edge cases, screens, endpoints? | [product-specs/](docs/product-specs/index.md) |
| How is the system shaped? Which files own a domain? | [ARCHITECTURE.md](docs/ARCHITECTURE.md) (domain map) |
| Why is it built this way? | [design-docs/](docs/design-docs/index.md) — design docs, [ADRs](docs/adr/README.md), DECISIONS |
| Which rules can't I break, and what enforces each? | [core-beliefs.md](docs/design-docs/core-beliefs.md) |
| How do I work, write or test a plan? | [PLANS.md](docs/PLANS.md) |
| What is in flight, what is done? | [generated/exec-plans.md](docs/generated/exec-plans.md) |
| What is known to be wrong? | [tech-debt-tracker.md](docs/exec-plans/tech-debt-tracker.md) |
| How do I boot, inspect, debug, deploy, back up? | [RELIABILITY.md](docs/RELIABILITY.md) — it links every runbook |
| Frontend rules: the proxy, the one fetcher, generated types, Next 16? | [FRONTEND.md](docs/FRONTEND.md), [web/AGENTS.md](web/AGENTS.md) |
| Threat model? Handling real data? | [SECURITY.md](docs/SECURITY.md) |
| How solid is each domain? | [QUALITY_SCORE.md](docs/QUALITY_SCORE.md) |
| Exact columns? Exact routes and shapes? | [db-schema.md](docs/generated/db-schema.md), [api-endpoints.md](docs/generated/api-endpoints.md) |
| Next 16, Access JWTs, Fly, Neon, SimpleFIN, openapi-typescript facts? | [references/](docs/references/index.md) |

## Commands

```bash
make dev           # postgres + api + web with hot reload, http://localhost:3000
make seed          # synthetic data into the local database (refuses a real one)
make test          # guards, doc checks, pytest, vitest — CI=true if the stack is already up
make lint          # ruff + mypy + eslint + tsc + prettier
make types         # regenerate web/src/lib/api-types.ts; `make types-check` fails on drift
make docs          # regenerate docs/generated/;          `make docs-check` fails on drift
make e2e           # Playwright against the deploy-shaped stack
make smoke         # the whole request path, deploy-shaped
make migrate m=""  # propose a migration; a human reviews every line before merge
make upgrade       # apply migrations to the local database
make backup        # full JSON export to data/backups/ — never open it
```

## Non-negotiables

One line each; the why and the enforcing check are in
[core-beliefs.md](docs/design-docs/core-beliefs.md).

1. [Never commit real financial data](docs/design-docs/core-beliefs.md#1-never-commit-real-financial-data), and never open `data/`.
2. [Code touches the data; context describes it](docs/design-docs/core-beliefs.md#2-code-touches-the-data-context-describes-the-data) — scripts read real files, sessions never do.
3. [The browser never calls the API directly](docs/design-docs/core-beliefs.md#4-the-browser-never-calls-the-api-directly) — no `NEXT_PUBLIC_API_URL`, no CORS.
4. [The Pydantic models are the contract](docs/design-docs/core-beliefs.md#5-the-pydantic-models-are-the-api-contract) — `make types` after any response-model change; never hand-edit `api-types.ts`.
5. [Money is `Decimal`, `NUMERIC(19,2)`, integer cents](docs/design-docs/core-beliefs.md#9-all-money-is-decimal-numeric192-integer-cents-on-the-wire) — never float.
6. [Net worth is ownership-adjusted and rounded once](docs/design-docs/core-beliefs.md#10-all-net-worth-math-is-ownership-adjusted-and-rounding-happens-once), in `services/ownership.adjust()`, per account, half-up.
7. [Every balance write appends a snapshot](docs/design-docs/core-beliefs.md#15-every-balance-write-appends-a-snapshot).
8. [The demo is a separate deployment and Neon project](docs/design-docs/core-beliefs.md#8-demo-mode-is-a-separate-deployment-against-a-separate-neon-project), never a flag.
9. [Every plan ships unit and functional tests](docs/design-docs/core-beliefs.md#24-every-plan-ships-unit-and-functional-tests).
10. [Never run `/feedback`, `/bug` or `/share` here](docs/design-docs/core-beliefs.md#3-do-not-run-feedback-bug-or-share-in-this-repo) — they upload the conversation.

## Layers

- **API** `api/app/`: models → schemas → services → routers → `main.py`. Routers get the
  session and identity only via `deps.py`; queries belong in services.
- **Web** `web/src/`: `lib/api-types.ts` → `lib/api.ts` → components → `app/` routes. Only
  `app/api/[...path]/route.ts` knows the API URL.
- Enforced by `api/tests/test_architecture.py` and `web/eslint.config.mjs`.
  [ARCHITECTURE.md#layers](docs/ARCHITECTURE.md#layers).

## When docs and code disagree

**The code wins — fix the doc in the same commit**, and say so in the message. `make test`
fails on broken links and anchors, unreachable docs, stale indexes, malformed plans and
stale generated docs; each failure names the rule, the doc, and the fix.

## Stack

FastAPI, Python 3.12, SQLAlchemy 2.0, Alembic, Pydantic v2, `uv` · Next.js 16 App Router,
TypeScript, Tailwind, `pnpm` · Neon Postgres · Docker → Fly.io · Cloudflare Access
([ADR 0007](docs/adr/0007-drop-passkeys.md)). `api/` and `web/` are two ecosystems side by
side, not a JS workspace. Prefer boring: one household, never build for scale.
