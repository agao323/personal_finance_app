# 088 — Recurring charges: subscriptions, their cadence, and what went up
Status: done
Wave: 9   Lane: S
Touches: none
Blocked by: 087
Read first: docs/ADVISOR.md#analyses, docs/PRODUCT.md#later--intended-unscheduled

## Goal
"Which subscriptions should I cancel?" has a factual half the app can answer: what recurs, how
often, what it costs a year, and what just got more expensive. Whether you *use* it is yours to
say.

## Acceptance criteria
- [x] `services/analysis/recurring.py`: per normalised merchant (087's normaliser) with at least
      three expense charges in the lookback — two for annual — the median interval picks a cadence
      (weekly 6–8 days, fortnightly 13–16, monthly 27–33, quarterly 85–95, annual 355–375), and at
      least 75% of intervals must fall inside it.
- [x] Per recurring merchant: cadence, typical amount (median, rounded once by `numbers.py`),
      whether the amount is fixed (all within 10% of the median), last charge, next expected,
      annualised cost, and a **price increase** when the latest charge is ≥ 5% and ≥ $1 above the
      median of the earlier ones.
- [x] **Lapsed, not active:** a merchant whose next expected charge is overdue by more than one
      interval is reported as lapsed. A cancelled subscription must not read as a cost you still
      carry.
- [x] Confidence `high` (fixed amount, ≥ 90% of intervals in cadence) or `medium`.
- [x] Tool `spend_recurring(lookback_months 6–24)`.
- [x] Tests: fixtures with a monthly subscription that rose from $15.49 to $17.99, an annual charge
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

## Done — 2026-09-27

- **After a price increase, a year costs the new price.** `annualised` uses the latest amount when
  an increase is detected and the typical one otherwise; quoting a subscription's year at the
  price it used to be understates exactly the thing the owner is asking about. The "typical" field
  still carries the median, and the increase is its own figure.
- Refunds are not charges: only outflows form a rhythm.
- The next expected charge is the last one plus the median interval rounded to whole days — a
  median of 30.5 is 31 days — and "lapsed" means overdue by more than one further interval.
- An annual charge needs two sightings, so it is only found with a lookback of 13 months or more;
  the tool's description says so, and a test pins that 12 months misses it.
