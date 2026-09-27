# 116 — Allocation: the household's mix, drift from target, and cash drag
Status: todo — order provisional
Wave: 12   Lane: —
Touches: none (finding kinds declared in 081)
Blocked by: 109, 113
Read first: docs/ADVISOR.md#numbers, docs/adr/0013-allocation-is-recorded-per-account-not-per-holding.md, docs/ARCHITECTURE.md#rounding

## Goal
"What's my asset allocation?" is answered from recorded percentages and ownership-adjusted
balances, split so the classes add up exactly to the accounts they came from.

## Acceptance criteria
- [ ] `ownership.split(amount, weights)`: largest-remainder allocation of an already-rounded amount,
      so the parts sum **exactly** to it. The second helper in `ownership.py`, and the module
      docstring updated to say rounding lives here for net worth and its breakdowns.
- [ ] `services/analysis/allocation.py`: per scope, each account's adjusted balance split by its
      allocation in force on `today`; totals by class; the share that is unknown; drift from the
      planning assumptions' target mix in percentage points; cash beyond the emergency-fund target
      (or six months of burn without one) as cash drag.
- [ ] Findings `allocation_drift` (any class more than 5 points from target) and `cash_drag`.
- [ ] Tool `get_allocation(scope)`, which states each allocation's effective date ("as entered on
      3 March").
- [ ] Tests: `split` as a `hypothesis` property — parts always sum to the whole, each part within one
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
