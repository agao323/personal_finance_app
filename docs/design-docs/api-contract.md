# The API contract

**The Pydantic models are the contract.** Nobody hand-writes or maintains an OpenAPI
spec, and the frontend never hand-writes an API response type. FastAPI *emits*
`openapi.json` from the Pydantic models that have to exist anyway, and the frontend
generates TypeScript from it:

```
Pydantic response models  →  openapi.json  →  openapi-typescript  →  web/src/lib/api-types.ts
        (source of truth)      (generated)        (generated, committed)
```

`make types` runs the pipeline (`api/scripts/export_openapi.py`, then `openapi-typescript`,
then prettier). `make types-check` regenerates and fails on any diff; CI runs it on every
branch. `api/openapi.json` is gitignored — the committed artifact is `api-types.ts`.

## Why

Decided in [DECISIONS.md](../DECISIONS.md) (2026-08-14, "API contract: FastAPI-generated
OpenAPI → generated TypeScript types"). A hand-maintained YAML spec goes stale because
nobody reads it — but dropping the *contract* entirely breaks multi-session work: a later
session writes a component against a response shape an earlier session never built, and
nothing catches it until runtime.

It mattered more here than usual because plans are implemented across sessions with no
shared memory, and in Wave 2 they ran **in three parallel lanes**. Ticket 012 declared
every model and every route up front — stubbed at `501` — so the contract existed before
any implementation did. After that, drift is a failed CI check rather than a merge conflict.

## Changing the contract

1. Change the Pydantic model (or add the route).
2. `make types`, and commit the regenerated `web/src/lib/api-types.ts` in the same commit.
3. If you added a route, add its row to [the endpoint table](#endpoints) — the contract
   test fails until you do.

During Wave 2 a response-shape change meant **stopping** and re-freezing in its own commit;
from Wave 3 on there is one worker and a plan changes the contract directly.
[ADR 0006](../adr/0006-contract-changes-during-wave-2.md) records the four Wave 2
re-freezes, why every workaround was worse, and the first non-additive change (047b removed
fourteen routes). The pipeline handles a deletion without special treatment — and would not
warn anyone if the deletion were a mistake.

## Rules the contract enforces on itself

`api/tests/test_contract.py`:

| Test | Rule |
|---|---|
| `test_documented_inventory_matches_the_app` | The table below equals the app's routes exactly |
| `test_every_documented_path_names_the_ticket_that_lands_it` | Every row ends in a ticket number |
| `test_every_stub_returns_501` | A declared-but-unimplemented route says so, rather than 404 — `LIVE_PATHS` is the ratchet |
| `test_money_fields_are_integer_cents` | Every `*_cents` field is an integer on the wire |
| `test_percentages_are_integer_basis_points` | Every `*_bps` field is an integer (`5000` = 50.00%) |
| `test_no_schema_field_is_a_bare_float` | No float anywhere, except `BurnWindow.months_of_runway`, a display ratio |
| `test_error_shape_is_defined_once` | One `ErrorResponse {detail, errors}`, so the frontend writes one handler |
| `test_every_non_public_route_requires_authentication` | Every route but `PUBLIC_PATHS` depends on `current_user` |
| `test_openapi_exports_without_a_database` | `make types` works in CI with nothing running |

Money is integer cents and percentages are integer basis points for the same reason:
2dp storage round-trips exactly through an integer, and a float cannot represent 33.33.
See [ownership-and-rounding.md](ownership-and-rounding.md#money).

On the web side, `api-types.ts` may only be imported with `import type` — it has no runtime
exports, and the lint rule keeps it that way. See [FRONTEND.md](../FRONTEND.md).

## Endpoints

The complete surface. Declared by ticket 012 and stubbed at `501` until the named ticket
implemented it; every route is live today.

**This table is checked against the running app by a test.** Adding a route without
listing it here, or listing one that does not exist, fails the suite — a stale
inventory is worse than none, because it is trusted. The ticket column is the one thing
only a person can supply; everything else about each route is generated into
[generated/api-endpoints.md](../generated/api-endpoints.md).

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
| GET | `/accounts/{account_id}/deletion-preview` | 063 |
| DELETE | `/accounts/{account_id}` | 063 |
| POST | `/accounts/{account_id}/balances` | 019 |
| POST | `/accounts/{account_id}/stakes` | 019 |
| POST | `/import/csv/preview` | 020 |
| POST | `/import/csv/commit` | 021 |
| GET POST | `/rules` | 022 |
| PATCH DELETE | `/rules/{rule_id}` | 022 |
| POST | `/rules/apply` | 022 |
| POST | `/rules/preview` | 033 |
| GET | `/categories` | 030 |
| GET | `/transactions` | 023 |
| PATCH | `/transactions/{transaction_id}` | 023 |
| POST | `/transactions/bulk-categorise` | 023 |
| POST | `/transactions/bulk-transfer` | 030 |
| GET | `/auth/session` | 034 |
| GET | `/cards` | 050 |
| POST | `/cards/{account_id}/perks` | 050 |
| PATCH | `/perks/{perk_id}` | 050 |
| POST DELETE | `/perks/{perk_id}/redemptions` | 050 |
| GET | `/perks/upcoming` | 050 |
| DELETE | `/perks/{perk_id}` | 054 |
| GET | `/perks/{perk_id}/history` | 054 |
| GET | `/cards/history` | 054 |
| GET | `/perks/{perk_id}/periods` | 068 |
| GET | `/perks/schedule` | 079 |
| GET POST | `/members` | 043 |
| PATCH | `/members/{member_id}` | 043 |

Query parameters, request bodies, and response shapes are defined in `api/app/schemas/`
and generated into `web/src/lib/api-types.ts`. They are deliberately not duplicated here —
a hand-maintained copy would go stale, which is the whole reason the contract is generated.

## See also

[ADR 0006](../adr/0006-contract-changes-during-wave-2.md) is the history;
[references/openapi-typescript-llms.txt](../references/openapi-typescript-llms.txt) is the
version-pinned note on the generator.
