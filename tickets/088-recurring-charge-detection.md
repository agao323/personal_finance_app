# 088 — Recurring charges: subscriptions, their cadence, and what went up
Status: todo
Wave: 9   Lane: S
Touches: none
Blocked by: 087
Read first: docs/ADVISOR.md#analyses, docs/PRODUCT.md#later--intended-unscheduled

## Goal
"Which subscriptions should I cancel?" has a factual half the app can answer: what recurs, how
often, what it costs a year, and what just got more expensive. Whether you *use* it is yours to
say.

## Acceptance criteria
- [ ] `services/analysis/recurring.py`: per normalised merchant (087's normaliser) with at least
      three expense charges in the lookback — two for annual — the median interval picks a cadence
      (weekly 6–8 days, fortnightly 13–16, monthly 27–33, quarterly 85–95, annual 355–375), and at
      least 75% of intervals must fall inside it.
- [ ] Per recurring merchant: cadence, typical amount (median, rounded once by `numbers.py`),
      whether the amount is fixed (all within 10% of the median), last charge, next expected,
      annualised cost, and a **price increase** when the latest charge is ≥ 5% and ≥ $1 above the
      median of the earlier ones.
- [ ] **Lapsed, not active:** a merchant whose next expected charge is overdue by more than one
      interval is reported as lapsed. A cancelled subscription must not read as a cost you still
      carry.
- [ ] Confidence `high` (fixed amount, ≥ 90% of intervals in cadence) or `medium`.
- [ ] Tool `spend_recurring(lookback_months 6–24)`.
- [ ] Tests: fixtures with a monthly subscription that rose from $15.49 to $17.99, an annual charge
      seen twice, a weekly habit, a quarterly service, one that stopped four months ago (lapsed),
      and a merchant with irregular charges that must **not** be called recurring.

## Files
- `api/app/services/analysis/recurring.py` (new)
- `api/app/advisor/tools/analysis.py`
- `api/tests/test_analysis_recurring.py`

## Notes
This pulls the read-only half of PRODUCT's Later "subscriptions I should cancel" forward. The
cancelling stays with the owner, at the merchant.

Detection is only as complete as the imports: a card whose CSV has not been imported for two
months has no recent charges to find. `data_health` (090) reports that, and the advisor is
expected to say so.
