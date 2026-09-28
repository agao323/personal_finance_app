# 117 — Projections to PRODUCT's FIRE bar
Status: done — except the returns dataset, an owner step
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
      runtime.** — **Owner step:** choose the dataset and accept its licence; the loader and its
      header rules are built.
- [x] `services/analysis/projections.py`, annual steps in `Decimal`, rounded once at output:
      three buckets from `tax_treatment` (HSA Roth-like after 65, education excluded);
      contributions from the trailing twelve months' savings (089) unless overridden; spending from
      trailing gross burn plus pre-65 healthcare until 65; withdrawals taxable → tax-deferred →
      Roth, with tax-deferred withdrawals taxed at the flat assumed rate and **not drawn before
      59½** — no 72(t) or Roth-ladder modelling, stated as a limitation.
- [x] Sequence risk: every historical start year as a rolling window, plus a seeded bootstrap of
      1,000 paths (fixed seed, reproducible).
- [x] Output: success rate for each withdrawal rate across the assumptions' band in 0.5-point steps,
      and the earliest retirement year reaching 90% success — **never a single "number"**. A test
      asserts that the result cannot be constructed without a band.
- [x] Every result carries the assumptions version id it used.
- [x] Tests: a deterministic single-sequence case checked by hand; bucket order; the 59½ rule; the
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

## Done — 2026-09-28

- **The returns table is not committed.** Choosing a public dataset means accepting its licence,
  and downloading it needs the owner's say-so; nothing was made up in its place. The loader
  requires `# source:` and `# licence:` header lines and the columns `year` plus every asset
  class, as real returns in decimal fractions. `default_returns()` refuses a missing or
  `# synthetic: true` table with `ProjectionUnavailableError("no_returns_table")`, so ticket 118's
  tools report a limitation instead of projecting on invented numbers. Tests run on
  `tests/fixtures/returns_synthetic.csv`, labelled synthetic in its header.
- A full run — 40 historical windows plus 1,000 bootstrap paths across sixty years — takes about
  half a second in `Decimal`; no paths were cut.
- **The withdrawal-rate band** is measured at the target retirement year (else the earliest 90%
  year, else 65): each path withdraws the rate times its own portfolio at retirement, held
  constant in real terms, and the result gives the success rate and the spending that rate
  supports on the median path. **The retirement-year band** uses the household's own spending
  plus pre-65 healthcare; success rises with the year, so a binary search finds the earliest
  reaching 90% on both the historical and bootstrap paths, and the band reports two years either
  side plus the target year.
- Buckets: taxable (cash accounts included), tax-deferred, Roth, and HSA from 65; education and
  property are left out, and so are accounts with no allocation, each named in the limitations.
  Savings go to taxable, which falls back to the overall mix when there is none. Spending and
  savings come from the last twelve complete months' cashflow, annualised.
- The 59½ rule is applied from the year the person turns 60, since only the birth year is known.
