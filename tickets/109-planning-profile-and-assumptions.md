# 109 — The planning profile and stated assumptions: schema, API, export
Status: todo — order provisional
Wave: 11   Lane: —
Touches: **migration** (after 108) · **contract**
Blocked by: 108
Read first: docs/ADVISOR.md#planning-profile-and-assumptions-wave-11-migration-in-109, docs/ADVISOR.md#advice-guardrails

## Goal
Every assumption advice depends on — expected return, inflation, the withdrawal band, healthcare
before 65, risk tolerance, a target mix — is written down in one place, visible, editable, and
versioned, so an answer can say which assumptions it used and a projection can be reproduced.

## Acceptance criteria
- [ ] `member_profiles` (birth year, target retirement year — per person) and
      `planning_assumptions` (append-only; the latest row wins) as sketched in ADVISOR.md, plus
      `tax_deferred_withdrawal_tax_bps` (default 1500) for 117's flat-rate simplification.
- [ ] Revision 0009 inserts one **defaults** row, marked as defaults, so there is always a set of
      assumptions to state — and the advisor says when it is using defaults.
- [ ] `CHECK` that the target mix sums to exactly 100; basis-point fields bounded.
- [ ] `GET PUT /planning/profile` (the current user's), `GET POST /planning/assumptions` (history,
      and append a new version). No update or delete of an existing version.
- [ ] Both tables in `EXPORTED` and `ExportRead`; `make types` run.
- [ ] Tests: append-only (no route mutates an old row); the mix constraint; defaults present after
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
