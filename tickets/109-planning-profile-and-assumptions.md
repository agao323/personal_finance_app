# 109 — The planning profile and stated assumptions: schema, API, export
Status: done
Wave: 11   Lane: —
Touches: **migration** (after 108) · **contract**
Blocked by: 108
Read first: docs/ADVISOR.md#planning-profile-and-assumptions-wave-11-migration-in-109, docs/ADVISOR.md#advice-guardrails

## Goal
Every assumption advice depends on — expected return, inflation, the withdrawal band, healthcare
before 65, risk tolerance, a target mix — is written down in one place, visible, editable, and
versioned, so an answer can say which assumptions it used and a projection can be reproduced.

## Acceptance criteria
- [x] `member_profiles` (birth year, target retirement year — per person) and
      `planning_assumptions` (append-only; the latest row wins) as sketched in ADVISOR.md, plus
      `tax_deferred_withdrawal_tax_bps` (default 1500) for 117's flat-rate simplification.
- [x] Revision 0009 inserts one **defaults** row, marked as defaults, so there is always a set of
      assumptions to state — and the advisor says when it is using defaults.
- [x] `CHECK` that the target mix sums to exactly 100; basis-point fields bounded.
- [x] `GET PUT /planning/profile` (the current user's), `GET POST /planning/assumptions` (history,
      and append a new version). No update or delete of an existing version.
- [x] Both tables in `EXPORTED` and `ExportRead`; `make types` run.
- [x] Tests: append-only (no route mutates an old row); the mix constraint; defaults present after
      migration; each member sees and edits only their own profile.

## Files
- `api/app/models/planning.py` (new), `api/alembic/versions/0009_planning.py` (new)
- `api/app/schemas/planning.py` (new), `api/app/routers/planning.py` (new)
- `api/app/schemas/export.py`, `api/app/routers/export.py`
- `api/tests/test_api_planning.py`

## Notes
Birth year is the most personal field in the schema and the projection needs nothing finer. Do not
add month or day.

**Monthly use: no.** This is set once and revisited rarely. It earns its place only through the
answers that quote it; if Wave 12 never ships, reconsider whether Wave 11 needs more than the
defaults row.

## Done — 2026-09-28

- `planning_assumptions` carries `is_default` and `created_by_user_id`. Revision 0009 inserts
  the defaults: 5% real return, 2.5% inflation, a 3%–4.5% withdrawal band, a flat 15% on
  tax-deferred withdrawals, moderate risk, and a 40/20/35/5/0 mix. They are placeholders, and
  the migration's docstring says so.
- On the wire every rate and the mix are basis points (4000 = 40.00%); the database keeps the
  mix as `NUMERIC(5,2)` and checks it totals exactly 100. The API checks the same and says what
  it totals ("totals 99.99%").
- Append-only is structural: `/planning/assumptions` has GET and POST and nothing else, and no
  path addresses a version. A test reads the OpenAPI document to hold that.
- Profiles are keyed to the signed-in member — there is no member id in the path to point at
  anyone else's. Birth year only.
- Drift-checked on a scratch database, including down to 0008 and back: no differences.
