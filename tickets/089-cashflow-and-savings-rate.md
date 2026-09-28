# 089 — Cashflow: income, net, and the savings rate
Status: todo
Wave: 9   Lane: S
Touches: none
Blocked by: 087
Read first: docs/ADVISOR.md#analyses, docs/PRODUCT.md#burn-and-runway

## Goal
Income has been classified since v1 so that it stays out of spend, and never shown. This computes
monthly income, spend, net and savings rate, so the advisor can answer "what's my savings rate" and
the Insights panel can report it.

## Acceptance criteria
- [ ] `services/analysis/cashflow.py`: per complete month in a window of 1–24 months — income (rows
      in `income`-kind categories, signed as stored), spend (from `spend.spend_totals`, so the same
      rules), net, and savings rate in bps **only when income > 0**. A negative savings rate is
      reported as negative, not clamped.
- [ ] Transfers are excluded from both sides. Months with no transactions are skipped.
- [ ] Not ownership-adjusted, exactly like spend. No scope parameter.
- [ ] Tool `cashflow_get(months)`.
- [ ] Tests: hand-computed months including a bonus month, a month with a refund, a month with a
      transfer pair (excluded), a month with no income (no savings rate), and one with no data
      (skipped).

## Files
- `api/app/services/analysis/cashflow.py` (new)
- `api/app/advisor/tools/analysis.py`
- `api/tests/test_analysis_cashflow.py`

## Notes
PRODUCT keeps **gross** burn on the runway tile, and this does not change that: runway answers "how
long if income stopped". Net figures appear in the advisor and the Insights panel, not on the tile.
An income *view* — a screen — is still PRODUCT Later; this is its computation.
