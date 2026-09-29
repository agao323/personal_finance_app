# 115 — Debt: avalanche or snowball, prepay or invest, and utilisation
Status: done
Wave: 12   Lane: —
Touches: none (finding kinds declared in 081)
Blocked by: 109, 112
Read first: docs/ADVISOR.md#analyses, docs/ADVISOR.md#advice-guardrails, docs/ADVISOR.md#numbers

## Goal
"Which debt first?" and "pay down the loan or invest?" get computed comparisons — both sides, with
the assumptions named — rather than a rule of thumb from the model.

## Acceptance criteria
- [x] `services/analysis/debt.py`: month-by-month amortisation in `Decimal`. **Interest is rounded
      to cents each month, half-up**, because that is what a lender's statement does — the one
      place a derived figure is rounded more than once, stated in the docstring and in
      `numbers.py`'s.
- [x] `strategies(extra_monthly)`: avalanche (highest APR first) and snowball (smallest balance
      first) — payoff order, months to debt-free, total interest, and the difference between them,
      computed here.
- [x] `prepay_vs_invest(account_id, extra_monthly, horizon_years ≤ 40)`: interest saved by
      prepaying versus the extra invested at the planning assumptions' real return; both end values
      and the difference; assumptions returned with the result. Mortgage-interest deductibility is
      excluded, and the result says so.
- [x] Credit utilisation per card and overall, from balances and limits.
- [x] Findings `high_interest_debt` (APR ≥ 8% and balance ≥ $500) and `credit_utilisation_high`
      (> 30%).
- [x] Tools `debt_compare_strategies(extra_monthly_cents)`, `debt_prepay_vs_invest(...)`; bounds
      on every argument.
- [x] Tests: a hand-computed amortisation for a known loan to the cent; avalanche and snowball on a
      three-debt fixture where they order differently; a promo APR that ends mid-schedule; a
      liability with no terms is reported as a limitation, never assumed at zero percent.

## Files
- `api/app/services/analysis/debt.py` (new)
- `api/app/services/findings.py`
- `api/app/advisor/tools/debt.py` (new)
- `api/tests/test_analysis_debt.py`

## Done — 2026-09-28

- `services/analysis/debt.py` schedules **whole balances**, as a lender amortises them, over the
  debts the view includes. Interest is rounded to cents each month, half-up; the docstring and
  `numbers.py`'s say it is the one exception. The hand-computed test: $1,000 at 12% and $100 a
  month clears in 11 months with $58.98 of interest.
- A debt's payment is its recorded minimum or, failing that, a level payment to its maturity
  date (rounded up so the last is not larger). A debt with no terms, or no payment to schedule,
  is a **limitation** in both tools, never 0%.
- Avalanche orders by the ongoing APR, not a promotion that will end; snowball by starting
  balance. Every minimum is paid, and the extra plus each freed minimum rolls down the order.
- `prepay_vs_invest` spends the same money each month two ways and measures investments less
  debt left at the horizon. The loan's rate is nominal, so the investment grows at the planning
  real return **and inflation** combined — both returned, with three stated exclusions (mortgage
  deductibility, tax on returns, steady returns). With a zero return, prepaying wins by exactly
  the interest saved; a test holds that.
- Findings: `high_interest_debt` (the rate in force today ≥ 8% on ≥ $500; its APR evidence is in
  basis points, since `EvidenceUnit` has no three-decimal unit and adding one is a contract
  change) and `credit_utilisation_high` per card above 30%.
- The eval world gives the mortgage and one card terms, leaving Travel Rewards without them;
  `goal-prepay-or-invest` is now active (goal_aware: 7). `expected.json` is unchanged.
