# 001 — Repo scaffold and tooling
Status: done
Wave: 0   Lane: —
Blocked by: none
Read first: docs/ARCHITECTURE.md#shape

## Goal
Empty repo becomes a working monorepo skeleton: `api/` (uv, Python 3.12) and `web/` (pnpm,
Next.js App Router, TypeScript, Tailwind) side by side, with linting and formatting
configured on both sides and a root Makefile that fronts every command.

## Acceptance criteria
- [x] `api/` initialised with uv; `pyproject.toml` pins Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2, pytest, pytest-cov, httpx, ruff, mypy, structlog
- [x] `web/` initialised with pnpm; Next.js App Router + TypeScript strict + Tailwind + eslint + prettier + vitest + Testing Library + MSW
- [x] Root `Makefile` with `dev`, `test`, `lint`, `types`, `seed`, `migrate`, `upgrade` targets (stubs that fail loudly where not yet implemented)
- [x] `.gitignore` excludes `data/`, `.env*`, `__pycache__`, `node_modules`, `.next`
- [x] `data/.gitkeep` and `data/README.md` exist
- [x] `make lint` passes on both sides
- [x] Tests: none — this is scaffolding. `make test` must exit 0 with zero collected tests on both sides.

## Files
- `api/pyproject.toml`
- `web/package.json`
- `web/tsconfig.json`
- `Makefile`
- `.gitignore`

## Notes
Do not add application code. Scaffolding only. Two ecosystems side by side — `web/` is NOT a
pnpm workspace containing `api/`.
