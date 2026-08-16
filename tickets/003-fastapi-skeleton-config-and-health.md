# 003 — FastAPI skeleton, config, health and readiness
Status: todo
Wave: 0   Lane: —
Blocked by: 002
Read first: docs/ARCHITECTURE.md#request-path, docs/ARCHITECTURE.md#operations

## Goal
The API boots with structured settings, a DB session dependency, and separate liveness and
readiness endpoints. pytest runs against a throwaway test database.

## Acceptance criteria
- [ ] `GET /health` — process liveness. Touches no database.
- [ ] `GET /ready` — reports database reachability
- [ ] Pydantic `Settings` reads config from env; fails loudly on missing required vars
- [ ] `DEMO_MODE` defined in Settings now (default false) even though nothing reads it until 037
- [ ] SQLAlchemy 2.0 engine + session dependency, pool configured for Neon's pooled endpoint
- [ ] **No CORS middleware.** The browser never calls this service directly — see ARCHITECTURE#request-path
- [ ] pytest fixture creating and tearing down a test database, with per-test transactional rollback
- [ ] Tests: unit for `Settings` validation incl. a missing required var; functional for `/health` and `/ready`, including `/ready` when the database is unreachable
- [ ] `make test` passes

## Files
- `api/app/main.py`
- `api/app/config.py`
- `api/app/db.py`
- `api/tests/conftest.py`
- `api/tests/test_health.py`

## Notes
Fly health checks probe `/health` only. If they probed `/ready`, a transient database blip
would restart otherwise-healthy instances.

The fixture creates the schema directly for now; ticket 009 switches it to
`alembic upgrade head` once migrations exist. Leave a `TODO(009)` marking the spot.
