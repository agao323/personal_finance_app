# 012 — API contract: models, stubbed routes, generated types
Status: todo
Wave: 1   Lane: —
Blocked by: 010, 011
Read first: docs/ARCHITECTURE.md#the-api-contract, docs/ARCHITECTURE.md#endpoints

## Goal
Every v1 request and response model exists, every route is declared and returns `501`, and
`api-types.ts` is generated from them. This freezes the contract and is the single thing that
lets Wave 2's three lanes run in parallel without drifting.

## Acceptance criteria
- [ ] Pydantic request and response models for every endpoint in ARCHITECTURE#endpoints
- [ ] Every route registered with its correct `response_model` and status codes, returning `501 Not Implemented`
- [ ] All money fields typed as **integer cents** in every schema
- [ ] Structured validation error shape defined once and reused
- [ ] A `current_user` dependency in `api/app/deps.py` returning the single configured user. **Ticket 034 replaces the implementation, not the signature.**
- [ ] `make types` run; `web/src/lib/api-types.ts` committed
- [ ] Route inventory in `docs/ARCHITECTURE.md#endpoints` matches the code exactly
- [ ] Tests: functional asserting every declared route returns 501, and that `openapi.json` contains every path in the inventory

## Files
- `api/app/schemas/*.py`
- `api/app/routers/*.py`
- `api/app/deps.py`
- `web/src/lib/api-types.ts`
- `docs/ARCHITECTURE.md`

## Notes
The single most important ticket in the plan. Once this lands, a frontend session and a
backend session cannot drift, because both are typed against the same generated file —
whichever lands first.

**Only this ticket and Wave 4 may edit `api-types.ts`.** A Wave 2 ticket that discovers it
needs a response-shape change stops, gets the change made in a re-freeze commit here, and
resumes. It does not hand-edit the generated file.

`current_user` existing now is what lets Lane A and Lane B write viewer-aware endpoints before
auth exists in Wave 3. No Wave 2 ticket should know that authentication isn't implemented yet.
