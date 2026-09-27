# 115 — Debt: avalanche or snowball, prepay or invest, and utilisation
Status: todo — order provisional
Wave: 12   Lane: —
Touches: none (finding kinds declared in 081)
Blocked by: 109, 112
Read first: docs/ADVISOR.md#analyses, docs/ADVISOR.md#advice-guardrails, docs/ADVISOR.md#numbers

## Goal
"Which debt first?" and "pay down the loan or invest?" get computed comparisons — both sides, with
the assumptions named — rather than a rule of thumb from the model.

## Acceptance criteria
- [ ] `services/analysis/debt.py`: month-by-month amortisation in `Decimal`. **Interest is rounded
      to cents each month, half-up**, because that is what a lender's statement does — the one
      place a derived figure is rounded more than once, stated in the docstring and in
      `numbers.py`'s.
- [ ] `strategies(extra_monthly)`: avalanche (highest APR first) and snowball (smallest balance
      first) — payoff order, months to debt-free, total interest, and the difference between them,
      computed here.
- [ ] `prepay_vs_invest(account_id, extra_monthly, horizon_years ≤ 40)`: interest saved by
      prepaying versus the extra invested at the planning assumptions' real return; both end values
      and the difference; assumptions returned with the result. Mortgage-interest deductibility is
      excluded, and the result says so.
- [ ] Credit utilisation per card and overall, from balances and limits.
- [ ] Findings `high_interest_debt` (APR ≥ 8% and balance ≥ $500) and `credit_utilisation_high`
      (> 30%).
- [ ] Tools `compare_debt_strategies(extra_monthly_cents)`, `compare_prepay_vs_invest(...)`; bounds
      on every argument.
- [ ] Tests: a hand-computed amortisation for a known loan to the cent; avalanche and snowball on a
      three-debt fixture where they order differently; a promo APR that ends mid-schedule; a
      liability with no terms is reported as a limitation, never assumed at zero percent.

## Files
- `api/app/services/analysis/debt.py` (new)
- `api/app/services/findings.py`
- `api/app/advisor/tools/debt.py` (new)
- `api/tests/test_analysis_debt.py`
