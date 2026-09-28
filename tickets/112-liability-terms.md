# 112 — Liability terms: APR, minimum payment, credit limit
Status: done
Wave: 12   Lane: —
Touches: **migration** (after 109) · **contract**
Blocked by: 109
Read first: docs/ADVISOR.md#liability-terms-wave-12-migration-in-112

## Goal
A loan or card records what it costs to carry — its rate, its minimum payment, its limit — so
"pay down the car loan or invest?" and "what's my utilisation?" stop being gaps.

## Acceptance criteria
- [x] `liability_terms` as sketched in ADVISOR.md; APR as `NUMERIC(6,3)` percent. Refused for
      accounts that are not liabilities, in the service, with a test.
- [x] Revision 0010, hand-reviewed; upgrade and downgrade tested.
- [x] `GET PUT /accounts/{account_id}/terms`. `as_of` defaults to today on save; terms whose `as_of`
      is more than 365 days old are reported stale.
- [x] `liability_terms` in `EXPORTED` and `ExportRead`; `make types` run.
- [x] Tool `debt_terms` (APR rendered to three decimals as a percentage).
- [x] Tests: refusal for an asset account; promo APR with an end date; staleness at 365 and 366
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

## Done — 2026-09-28

- On the wire an APR is **thousandths of a percent** (`apr_pct_thousandths: 6875` is 6.875%),
  because basis points stop at two decimals. The advisor's renderer gained that unit
  (`_pct_thousandths` → `6.875%`, key `apr_pct`), and the grounding check matches it exactly and
  rounded to two, one or no decimals — "6.88%" and "7%" for 6.875% are matched, "6.876%" is not.
- `GET /accounts/{id}/terms` returns null until terms are recorded; `PUT` records every term at
  once, `as_of` defaulting to today, and refuses a non-liability with a 422 from the service.
  The read carries `effective_apr_pct_thousandths` (a promotion through its end date, then the
  APR) and `stale` (more than 365 days, tested at 365 and 366).
- The database holds the rest: APR 0–100, a promotional rate only with its end date, a positive
  limit and term.
- `debt_terms` lists every open liability in the view with its terms, or `terms_recorded:
  false` so the model names the gap. Utilisation uses the whole balance against the limit; the
  view's share is reported beside it.
- Drift-checked on a scratch database, including down to 0009 and back: no differences.
