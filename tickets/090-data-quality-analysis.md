# 090 — Data quality: stale balances, missing imports, uncategorised spend, unmarked transfers
Status: todo
Wave: 9   Lane: S
Touches: none
Blocked by: 087
Read first: docs/ADVISOR.md#analyses, docs/ARCHITECTURE.md#closed-accounts-and-carry-forward, docs/ARCHITECTURE.md#transfers

## Goal
Before the advisor recommends anything it can ask how trustworthy the numbers are: which balances
are stale, which accounts have not had transactions imported lately, how much spend is
uncategorised, and which transactions look like transfers nobody marked.

## Acceptance criteria
- [ ] `services/analysis/data_quality.py` returns, per account: last snapshot date and stale flag,
      last transaction date, and whether transactions have ever been imported; overall:
      uncategorised share of last complete month's spend and count; earliest snapshot (history
      coverage); and **possible unmarked transfers**.
- [ ] A possible unmarked transfer is two transactions on **different accounts** with **exactly
      opposite amounts** of at least $50, posted within 3 days, neither in a transfer group nor in a
      `transfer`-kind category. Each transaction belongs to at most one pair, matched by closest
      date.
- [ ] Tool `get_data_health()`.
- [ ] Tests: a stale balance at 90 and 91 days; an account with no transactions in 36 days; a true
      pair; a near-miss (different amount by a cent, same account, four days apart) that must not
      pair; three candidates competing for one partner.

## Files
- `api/app/services/analysis/data_quality.py` (new)
- `api/app/advisor/tools/analysis.py`
- `api/tests/test_analysis_data_quality.py`

## Notes
Suggestions only. Marking a transfer stays a person's action on `/transactions`, which is why this
does not pull PRODUCT's "automatic transfer-pair detection" forward — it pulls forward the part
that reads. An unmarked transfer is worth a `warning`: counted as spend, it inflates burn and makes
runway read short.
