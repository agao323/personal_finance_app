# 087 — Spend analyses: period comparison, trends and anomalies, top merchants
Status: todo
Wave: 9   Lane: S
Touches: none
Blocked by: 082, 083
Read first: docs/ADVISOR.md#analyses, docs/ADVISOR.md#numbers, docs/PRODUCT.md#burn-and-runway

## Goal
"Dining this quarter vs last", "is grocery spending trending up", "anything unusual this month"
and "where does the dining money go" each have a deterministic answer, computed in Python from
the spend service's own rules, and available as an advisor tool.

## Acceptance criteria
- [ ] `services/analysis/numbers.py`: the **rounding site for derived figures** — `quantize_money`
      and `to_bps`, half-up, at full `Decimal` precision until then. Its docstring names
      `ownership.py` as the rounding site for net worth, and this as the one for everything that
      divides.
- [ ] `spend_trends.compare(period_a, period_b, group_by, category_id)`: per-bucket totals over two
      explicit windows via `spend.spend_totals`, change, and change in bps. A partial period is
      compared like-for-like on elapsed days and says so, with the full prior total alongside.
- [ ] `spend_trends.monthly(category_id, months, today)`: complete months only; a month is
      anomalous above **1.5×** the median of the prior six complete months **and** by at least
      **$50**. Months with no transactions are skipped, via runway's helper made public.
- [ ] `spend_trends.top_merchants(period, category_id, limit ≤ 10)`: expense by normalised
      merchant — upper-cased, `SQ *`, `TST*`, `PAYPAL *` and similar prefixes and trailing store
      numbers removed — with count, total and share.
- [ ] Tools in `advisor/tools/analysis.py`: `spend_compare`, `spend_trend`, `spend_top_merchants`.
- [ ] Tests, all hand-computed: calendar Q3 vs Q2; a partial quarter on 20 August compared
      like-for-like; an anomaly exactly at 1.5× and at $50 (both edges); a month with no data
      skipped rather than read as zero; a table of merchant strings and their normalised forms.

## Files
- `api/app/services/analysis/numbers.py` (new)
- `api/app/services/analysis/spend_trends.py` (new)
- `api/app/advisor/tools/analysis.py` (new)
- `api/app/services/runway.py` (make the has-data helper public)
- `api/tests/test_analysis_spend_trends.py`

## Notes
`spend_by_category` compares against the equal-length window immediately before, which is right
for the dashboard and wrong for "this quarter vs last": a 92-day window before 1 July starts on
31 March. That is why this ticket compares two explicit windows rather than reusing the prior
period.

The thresholds are constants at the top of the module, like `URGENT_WITHIN` in `perks.py`.
