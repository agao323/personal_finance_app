# CLAUDE.md

Personal finance app. One household (Allen, plus a partner later). Read this, then `tickets/README.md`.

**This file is loaded into every session — keep it short. Detail lives in `docs/`.**

## Start of every session

1. Read `tickets/README.md` for the workflow rules.
2. Take the lowest-numbered ticket with `Status: todo` **in your assigned lane**. Check its `Blocked by`.
3. Read that ticket. Read only the `docs/` files it lists under **Read first**.
4. Implement. Do not exceed the ticket's scope — if you find adjacent work, add a ticket, don't do it.
5. Finish with green tests + a commit. Set `Status: done`.

## Stack

- **Backend:** FastAPI, Python 3.12, SQLAlchemy 2.0, Alembic, Pydantic v2. Package manager: `uv`.
- **Frontend:** Next.js (App Router), TypeScript, Tailwind. Package manager: `pnpm`.
- **DB:** Neon Postgres. **Deploy:** Docker → Fly.io. **Auth:** Cloudflare Access + passkeys.
- Repo layout: `api/` and `web/` at top level. Not a JS workspace — two ecosystems side by side.

## Commands

```bash
make dev          # docker compose up: postgres + api + web
make test         # both suites
make lint         # ruff + mypy + eslint + tsc
make types        # regenerate web/src/lib/api-types.ts from the API's OpenAPI
make seed         # synthetic data into the local dev database
make migrate m="" # alembic revision --autogenerate
make upgrade      # alembic upgrade head
```

## Rules that are not negotiable

1. **Never commit real financial data.** `data/` is gitignored. Dev and tests run on generated synthetic data only.
2. **Code touches the data; context describes the data.** Write scripts that process files. Do not read real financial values into your context to work with them. See `docs/SECURITY.md`.
3. **The browser never calls the API directly.** All traffic goes to the Next.js origin, which proxies to a privately-networked API. There is no `NEXT_PUBLIC_API_URL` and no CORS config. See `docs/ARCHITECTURE.md#request-path`.
4. **The Pydantic models are the API contract.** After changing any response model, run `make types` and commit the regenerated file. CI fails on drift. In Wave 2, changing a response model means stopping and re-freezing — see `tickets/README.md`.
5. **All money is `Decimal`** in Python, `NUMERIC(19,2)` in Postgres, **integer cents** over the wire. Never float. Never `Float` in a SQLAlchemy column.
6. **All net worth math is ownership-adjusted**, and rounding happens exactly once — in `services/ownership.py`, per account, `ROUND_HALF_UP`. There is no code path that sums raw balances. See `docs/ARCHITECTURE.md#users-and-ownership`.
7. **Every balance write appends a snapshot.** History is never reconstructable after the fact.
8. **Demo mode is a separate deployment against a separate Neon project.** Never a runtime flag over real data. Never a branch of the real project.
9. **Every ticket ships unit and functional tests.** See `tickets/README.md#tests`.
10. Do not run `/feedback`, `/bug`, or `/share` in this repo — they upload conversation history.

## Conventions

- Backend tests: `pytest`, colocated in `api/tests/`, one file per module under test.
- Frontend tests: `vitest` + Testing Library + MSW. Playwright for the two E2E smoke tests only.
- Migrations are always reviewed by a human before merge. Never `--autogenerate` and commit blind.
- Commit format: `<ticket-id>: <imperative summary>` e.g. `010: add effective-dated ownership stakes`.
- Prefer boring. This app has one household; do not build for scale.
