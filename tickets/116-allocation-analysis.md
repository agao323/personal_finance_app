# 116 — Allocation: the household's mix, drift from target, and cash drag
Status: done
Wave: 12   Lane: —
Touches: none (finding kinds declared in 081)
Blocked by: 109, 113
Read first: docs/ADVISOR.md#numbers, docs/adr/0013-allocation-is-recorded-per-account-not-per-holding.md, docs/ARCHITECTURE.md#rounding

## Goal
"What's my asset allocation?" is answered from recorded percentages and ownership-adjusted
balances, split so the classes add up exactly to the accounts they came from.

## Acceptance criteria
- [x] `ownership.split(amount, weights)`: largest-remainder allocation of an already-rounded amount,
      so the parts sum **exactly** to it. The second helper in `ownership.py`, and the module
      docstring updated to say rounding lives here for net worth and its breakdowns.
- [x] `services/analysis/allocation.py`: per scope, each account's adjusted balance split by its
      allocation in force on `today`; totals by class; the share that is unknown; drift from the
      planning assumptions' target mix in percentage points; cash beyond the emergency-fund target
      (or six months of burn without one) as cash drag.
- [x] Findings `allocation_drift` (any class more than 5 points from target) and `cash_drag`.
- [x] Tool `allocation_get(scope)`, which states each allocation's effective date ("as entered on
      3 March").
- [x] Tests: `split` as a `hypothesis` property — parts always sum to the whole, each part within one
      cent of its exact share; the 50% rental in both scopes; an account with unknown allocation
      reported as unknown, never folded into another class.

## Files
- `api/app/services/ownership.py`
- `api/app/services/analysis/allocation.py` (new)
- `api/app/services/findings.py`
- `api/app/advisor/tools/allocation.py` (new)
- `api/tests/test_analysis_allocation.py`

## Notes
`ownership.py` is the most carefully guarded file in the repo. The change is one new pure function
with property tests, and nothing existing moves. Review it as such.

## Done — 2026-09-28

- `ownership.split` is one new pure function; nothing existing moved. It refuses an amount not
  already in cents, no weights, all-zero or negative weights. Property-tested with hypothesis
  (parts sum to the whole; each within a cent of its exact share), plus the worked examples.
  ARCHITECTURE#rounding names it beside `adjust`.
- The mix splits each asset account's ownership-adjusted balance from `net_worth`, so class
  totals sum exactly to total assets (tested). Unknown stays in its own total.
- **Drift is measured over the investable base** — recorded accounts plus cash — because the
  target mix has no place for a house; property and vehicles are left out. It is withheld when
  half or more of that base is unknown. The finding names the class furthest off target.
- **Cash drag** uses the active emergency-fund goal's months, or six, times the last six complete
  months' spending (the household's in both scopes, as runway's is). The finding needs $5,000
  beyond the fund; `CASH_DRAG_MIN` sits in findings' threshold table with the 5-point drift.
- `allocation_get` returns each recorded allocation's `entered_on` and tells the model to say "as
  entered on".
- The eval world's 401k is 70/20/10 as entered on 3 March and the brokerage all US stocks;
  `goal-allocation-drift` is active (goal_aware: 8). `expected.json` is unchanged.
