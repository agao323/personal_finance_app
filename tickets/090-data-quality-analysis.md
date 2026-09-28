# 090 — Data quality: stale balances, missing imports, uncategorised spend, unmarked transfers
Status: done
Wave: 9   Lane: S
Touches: none
Blocked by: 087
Read first: docs/ADVISOR.md#analyses, docs/ARCHITECTURE.md#closed-accounts-and-carry-forward, docs/ARCHITECTURE.md#transfers

## Goal
Before the advisor recommends anything it can ask how trustworthy the numbers are: which balances
are stale, which accounts have not had transactions imported lately, how much spend is
uncategorised, and which transactions look like transfers nobody marked.

## Acceptance criteria
- [x] `services/analysis/data_quality.py` returns, per account: last snapshot date and stale flag,
      last transaction date, and whether transactions have ever been imported; overall:
      uncategorised share of last complete month's spend and count; earliest snapshot (history
      coverage); and **possible unmarked transfers**.
- [x] A possible unmarked transfer is two transactions on **different accounts** with **exactly
      opposite amounts** of at least $50, posted within 3 days, neither in a transfer group nor in a
      `transfer`-kind category. Each transaction belongs to at most one pair, matched by closest
      date.
- [x] Tool `data_health()`.
- [x] Tests: a stale balance at 90 and 91 days; an account with no transactions in 36 days; a true
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

## Done — 2026-09-27

- **One pair per transaction, closest first, ties by id.** Candidates are sorted by days apart,
  then outflow id, then inflow id, and taken greedily, so three candidates for one outflow give one
  pair — deterministic, and the same answer on every run.
- Pairs are looked for over the last 90 days and listed newest first, at most 20 per call.
- Staleness reuses `balances.STALE_AFTER`, so "stale" means exactly what it means on the dashboard:
  90 days is not stale, 91 is.
- Only open accounts are reported; a closed account's old balance is history, not a prompt.
