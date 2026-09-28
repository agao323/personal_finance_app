# 108 — Goals: schema, API, export
Status: done
Wave: 11   Lane: —
Touches: **migration** (after 095) · **contract**
Blocked by: 095, 093
Read first: docs/ADVISOR.md#goals-wave-11-migration-in-108, docs/ARCHITECTURE.md#users-and-ownership

## Goal
The household can record what it is aiming for — a monthly spending limit on a category, an
emergency fund measured in months, a savings target by a date — so advice can be measured against
something other than a default.

## Acceptance criteria
- [x] `goals` and `goal_accounts` exactly as sketched in ADVISOR.md, with `CHECK` constraints that
      make each kind's required fields required (a `spending_limit` has a category and a monthly
      amount; an `emergency_fund` has target months; a `savings_target` has an amount and at least
      one linked account, enforced in the service).
- [x] Revision 0008, hand-reviewed; upgrade and downgrade tested.
- [x] `GET POST /goals`, `PATCH DELETE /goals/{goal_id}`. `GoalRead` declares
      `progress: GoalProgress | null`, **null until 111 computes it** — declared now so 111 needs
      no contract change.
- [x] A household goal has no owner; a personal goal's owner is the current user.
- [x] `goals` and `goal_accounts` in `EXPORTED` and `ExportRead`; `make types` run.
- [x] Tests: each kind's constraints at the database and at the API; a goal linked to a closed
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

## Done — 2026-09-28

- `goal_kind` and `goal_status` are Postgres enums like the rest of the schema's enums; Wave 12
  adds `debt_free` and `retirement` in its own migration. Seven `CHECK` constraints hold each
  kind's fields — required ones present, other kinds' absent, targets positive.
- On the wire: money in cents, months in tenths (`target_months_tenths: 60` is 6.0 months), and
  `view` for whose goal it is — `household` has no owner, `mine` is the current user's — the same
  word the rest of the app uses for the toggle.
- **Personal goals are their owner's alone**: another member gets a 404, as with conversations.
- The service refuses each rule with a readable 422 first: a savings target with no linked or
  a closed account, a category on anything but a spending limit, linked accounts on anything but
  a savings target. An edit is checked against the same rules.
- `GoalProgress` is declared whole, one shape for every kind with the unused fields null, so 111
  fills it without a contract change.
- Drift-checked against a scratch database, including down to 0007 and back: no goal
  differences.
- Found in passing and fixed in the tests: the "switch to the partner" fixture left the cached
  settings on the partner after the test, which leaked into the next one. It now clears them on
  the way out (here and in `test_api_advisor.py`).
