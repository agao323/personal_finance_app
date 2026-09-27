# 002 — Local dev via Docker Compose
Status: done
Wave: 0   Lane: —
Blocked by: 001
Read first: docs/ARCHITECTURE.md#shape, docs/ARCHITECTURE.md#request-path

## Goal
`make dev` brings up Postgres, the API, and the web app locally in Docker with hot reload on
both, so no session ever needs host-installed Python or Node to run the stack.

## Acceptance criteria
- [x] `docker-compose.yml` with `postgres`, `api`, `web` services
- [x] `api/Dockerfile` and `web/Dockerfile`, multi-stage, production-capable — `web` uses Next.js standalone output
- [x] Source mounted for hot reload in the compose override; the base Dockerfiles stay deploy-ready — verified: WatchFiles reloads the API on edit, `next dev` serves the web app
- [x] Postgres data persisted in a named volume
- [x] The API service is **not** published to the host; only `web` maps a port
- [x] `.env.example` documents every variable, including the split between the public web origin and the internal API URL
- [x] `make dev` starts all three and the web app reaches the API through its server-side proxy — completed in 004, which added the route handler and extended `make smoke` to exercise the full browser path.
- [x] Tests: a `make smoke` target asserting all three containers report healthy and the web app can reach the API

## Files
- `docker-compose.yml`
- `docker-compose.override.yml`
- `api/Dockerfile`
- `web/Dockerfile`
- `.env.example`

## Notes
The Dockerfiles written here ship to Fly. Getting them production-shaped now avoids rewriting
in 008.

Not publishing the API port locally is deliberate: it mirrors production, where the API has no
public address, and it means a hand-written browser fetch to the API fails in dev instead of
silently working and breaking on deploy.
