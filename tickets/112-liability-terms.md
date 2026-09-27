# 112 — Liability terms: APR, minimum payment, credit limit
Status: todo — order provisional
Wave: 12   Lane: —
Touches: **migration** (after 109) · **contract**
Blocked by: 109
Read first: docs/ADVISOR.md#liability-terms-wave-12-migration-in-112

## Goal
A loan or card records what it costs to carry — its rate, its minimum payment, its limit — so
"pay down the car loan or invest?" and "what's my utilisation?" stop being gaps.

## Acceptance criteria
- [ ] `liability_terms` as sketched in ADVISOR.md; APR as `NUMERIC(6,3)` percent. Refused for
      accounts that are not liabilities, in the service, with a test.
- [ ] Revision 0010, hand-reviewed; upgrade and downgrade tested.
- [ ] `GET PUT /accounts/{account_id}/terms`. `as_of` defaults to today on save; terms whose `as_of`
      is more than 365 days old are reported stale.
- [ ] `liability_terms` in `EXPORTED` and `ExportRead`; `make types` run.
- [ ] Tool `get_liability_terms` (APR rendered to three decimals as a percentage).
- [ ] Tests: refusal for an asset account; promo APR with an end date; staleness at 365 and 366
      days; export includes terms.

## Files
- `api/app/models/liability_terms.py` (new), `api/alembic/versions/0010_liability_terms.py` (new)
- `api/app/schemas/account.py`, `api/app/routers/accounts.py`
- `api/app/schemas/export.py`, `api/app/routers/export.py`
- `api/tests/test_api_liability_terms.py`

## Notes
Not effective-dated, unlike stakes: a rate's history rarely changes an answer, and `as_of` carries
the staleness that does. If variable-rate history turns out to matter, that is a new table, not a
column on this one.
