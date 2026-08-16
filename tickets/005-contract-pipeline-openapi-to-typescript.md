# 005 — Contract pipeline: OpenAPI to TypeScript
Status: todo
Wave: 0   Lane: —
Blocked by: 004
Read first: docs/ARCHITECTURE.md#the-api-contract

## Goal
`make types` exports the API's `openapi.json` and generates `web/src/lib/api-types.ts` from
it via `openapi-typescript`. The generated file is committed. This is the mechanism that
keeps the three Wave 2 lanes in sync.

## Acceptance criteria
- [ ] Script exports `openapi.json` from the FastAPI app without booting a server
- [ ] `openapi-typescript` generates `web/src/lib/api-types.ts`
- [ ] `make types` runs both steps
- [ ] Generated file is committed and its header marks it generated — do not edit
- [ ] `apiFetch` from 004 is retyped against the generated types, with path and response type inferred from the route string
- [ ] A documented drift check: regenerate, fail if `git diff` is non-empty
- [ ] Tests: unit asserting the export script emits a schema containing a known path and that the generated file compiles under `tsc`

## Files
- `Makefile`
- `api/scripts/export_openapi.py`
- `web/src/lib/api-types.ts`
- `web/src/lib/api.ts`
- `web/package.json`

## Notes
The single most important ticket in Wave 0. Everything downstream depends on it — 012 freezes
the whole contract through this pipeline, and Wave 2's parallelism rests on that freeze. If
the generated types are awkward to consume, fix it **here**, not by working around it in 20
components.
