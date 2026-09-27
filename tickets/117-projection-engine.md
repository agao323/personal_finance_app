# 117 — Projections to PRODUCT's FIRE bar
Status: todo — order provisional
Wave: 12   Lane: —
Touches: none
Blocked by: 089, 109, 113, 116
Read first: docs/PRODUCT.md#later--intended-unscheduled, docs/ADVISOR.md#projections, docs/ADVISOR.md#numbers

## Goal
"Can we retire at 50?" gets a band, not a number: success across a range of withdrawal rates,
across historical sequences of returns, with taxable, tax-deferred and Roth money kept apart and
healthcare before 65 costed — every assumption returned alongside.

## Acceptance criteria
- [ ] `api/app/services/analysis/returns.csv`: annual real returns by asset class from a public
      dataset, committed, with its source and licence in the file header. **Nothing fetched at
      runtime.**
- [ ] `services/analysis/projections.py`, annual steps in `Decimal`, rounded once at output:
      three buckets from `tax_treatment` (HSA Roth-like after 65, education excluded);
      contributions from the trailing twelve months' savings (089) unless overridden; spending from
      trailing gross burn plus pre-65 healthcare until 65; withdrawals taxable → tax-deferred →
      Roth, with tax-deferred withdrawals taxed at the flat assumed rate and **not drawn before
      59½** — no 72(t) or Roth-ladder modelling, stated as a limitation.
- [ ] Sequence risk: every historical start year as a rolling window, plus a seeded bootstrap of
      1,000 paths (fixed seed, reproducible).
- [ ] Output: success rate for each withdrawal rate across the assumptions' band in 0.5-point steps,
      and the earliest retirement year reaching 90% success — **never a single "number"**. A test
      asserts that the result cannot be constructed without a band.
- [ ] Every result carries the assumptions version id it used.
- [ ] Tests: a deterministic single-sequence case checked by hand; bucket order; the 59½ rule; the
      bootstrap reproducible run to run; a run with unknown allocation reports the unknown share
      rather than assuming one.

## Files
- `api/app/services/analysis/returns.csv` (new)
- `api/app/services/analysis/projections.py` (new)
- `api/tests/test_analysis_projections.py`

## Notes
PRODUCT says a calculator that multiplies expenses by 25 is not worth building. The test that
refuses a single-number result is how that sentence survives future sessions.

If a thousand paths across sixty years is slow in `Decimal`, cut the paths before switching to
float. Rule 5 does not have a performance exception.
