# 108 — Goals: schema, API, export
Status: todo — order provisional; see 080's note on `note_limitation`
Wave: 11   Lane: —
Touches: **migration** (after 095) · **contract**
Blocked by: 095, 093
Read first: docs/ADVISOR.md#goals-wave-11-migration-in-108, docs/ARCHITECTURE.md#users-and-ownership

## Goal
The household can record what it is aiming for — a monthly spending limit on a category, an
emergency fund measured in months, a savings target by a date — so advice can be measured against
something other than a default.

## Acceptance criteria
- [ ] `goals` and `goal_accounts` exactly as sketched in ADVISOR.md, with `CHECK` constraints that
      make each kind's required fields required (a `spending_limit` has a category and a monthly
      amount; an `emergency_fund` has target months; a `savings_target` has an amount and at least
      one linked account, enforced in the service).
- [ ] Revision 0008, hand-reviewed; upgrade and downgrade tested.
- [ ] `GET POST /goals`, `PATCH DELETE /goals/{goal_id}`. `GoalRead` declares
      `progress: GoalProgress | null`, **null until 111 computes it** — declared now so 111 needs
      no contract change.
- [ ] A household goal has no owner; a personal goal's owner is the current user.
- [ ] `goals` and `goal_accounts` in `EXPORTED` and `ExportRead`; `make types` run.
- [ ] Tests: each kind's constraints at the database and at the API; a goal linked to a closed
      account is refused; export includes a goal.

## Files
- `api/app/models/goal.py` (new), `api/alembic/versions/0008_goals.py` (new)
- `api/app/schemas/goal.py` (new), `api/app/routers/goals.py` (new)
- `api/app/schemas/export.py`, `api/app/routers/export.py`
- `api/tests/test_api_goals.py`

## Notes
Progress is computed, never stored — the same reason current balance is derived from snapshots
rather than written onto `accounts`. `debt_free` and `retirement` goal kinds wait for Wave 12; an
enum value is a migration, so add them there deliberately rather than here speculatively.
