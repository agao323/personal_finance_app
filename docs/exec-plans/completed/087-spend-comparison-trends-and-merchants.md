# 087 — Spend analyses: period comparison, trends and anomalies, top merchants
Status: done
Wave: 9   Lane: S
Touches: none
Blocked by: 082, 083
Read first: docs/ADVISOR.md#analyses, docs/ADVISOR.md#numbers, docs/PRODUCT.md#burn-and-runway

## Goal
"Dining this quarter vs last", "is grocery spending trending up", "anything unusual this month"
and "where does the dining money go" each have a deterministic answer, computed in Python from
the spend service's own rules, and available as an advisor tool.

## Acceptance criteria
- [x] `services/analysis/numbers.py`: the **rounding site for derived figures** — `quantize_money`
      and `to_bps`, half-up, at full `Decimal` precision until then. Its docstring names
      `ownership.py` as the rounding site for net worth, and this as the one for everything that
      divides.
- [x] `spend_trends.compare(period_a, period_b, group_by, category_id)`: per-bucket totals over two
      explicit windows via `spend.spend_totals`, change, and change in bps. A partial period is
      compared like-for-like on elapsed days and says so, with the full prior total alongside.
- [x] `spend_trends.monthly(category_id, months, today)`: complete months only; a month is
      anomalous above **1.5×** the median of the prior six complete months **and** by at least
      **$50**. Months with no transactions are skipped, via runway's helper made public.
- [x] `spend_trends.top_merchants(period, category_id, limit ≤ 10)`: expense by normalised
      merchant — upper-cased, `SQ *`, `TST*`, `PAYPAL *` and similar prefixes and trailing store
      numbers removed — with count, total and share.
- [x] Tools in `advisor/tools/analysis.py`: `spend_compare`, `spend_trend`, `spend_top_merchants`.
- [x] Tests, all hand-computed: calendar Q3 vs Q2; a partial quarter on 20 August compared
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

## Done — 2026-09-27

- **A real bug, caught by this ticket's test, fixed in 083's renderer.** `total_change_cents` and
  `total_change_bps` both rendered as `total_change`, and the percentage silently overwrote the
  dollar figure. Percentages now render as `*_pct`, and the renderer raises if any two fields
  would ever share a key. ADVISOR.md's example updated to the real shape.
- A category filter is inclusive of children: asking about Food includes Groceries and
  Restaurants. `monthly` uses the parent rollup for a parent and the leaf totals for a leaf.
- The anomaly rule is strict: $150.00 against a $100 median is exactly 1.5x and **not** flagged;
  $150.01 is. A median needs three months of data, the floor runway already uses.
- Merchants group on `categorize.subject_of` — merchant first, description as the fallback — so
  "where the money goes" matches what rules match against. A charge with neither groups as
  `UNKNOWN MERCHANT`.
- `runway.has_any_transaction` is public; every analysis skips months without data through it.
