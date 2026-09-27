# 091 — Why net worth moved: change attributed to accounts, with reasons
Status: todo
Wave: 9   Lane: S
Touches: none
Blocked by: 087
Read first: docs/ADVISOR.md#analyses, docs/ARCHITECTURE.md#users-and-ownership, docs/ARCHITECTURE.md#closed-accounts-and-carry-forward

## Goal
"Why did net worth drop in March?" gets an exact decomposition: which accounts moved, by how much,
and whether the movement was a change in value, an account opening or closing, a stake changing
hands, or a balance nobody updated.

## Acceptance criteria
- [ ] `services/analysis/networth_change.py` computes `net_worth` at both dates in the same scope and
      returns per-account delta of the **adjusted** contribution, with reasons: `opened`, `closed`,
      `stake_changed`, `not_updated` (no snapshot inside the window — a flat line that is
      carry-forward, not stability), `stale`.
- [ ] **Per-account deltas sum exactly to the total change**, in both scopes. No rounding happens
      here; every figure is a difference of figures `ownership.adjust` already rounded.
- [ ] Kind subtotals (liquid, illiquid, liabilities).
- [ ] Where an investment account's transfers are imported, `flows` reports money moved in or out in
      the window and the implied change in value, labelled an estimate. Where they are not, `flows`
      is absent rather than zero.
- [ ] `coverage`: if `from_date` precedes the first snapshot, the result says the history does not
      reach that far instead of treating the account as zero.
- [ ] Tool `explain_net_worth_change(scope, from_date, to_date)`.
- [ ] Tests: reconciliation as a property test (`hypothesis`) over generated snapshot histories; a
      stake change inside the window; a car closed inside it; an account updated in January and not
      since; the seed's 50% rental in both scopes.

## Files
- `api/app/services/analysis/networth_change.py` (new)
- `api/app/advisor/tools/analysis.py`
- `api/tests/test_analysis_networth_change.py`

## Notes
The reconciliation property is the whole point. ARCHITECTURE's rounding rule exists so the figure
on screen equals the sum of the rows beneath it; an explanation whose parts did not add up to the
change it explains would break the same trust from the other direction.
