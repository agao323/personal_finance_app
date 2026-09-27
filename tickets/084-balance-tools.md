# 084 — Balance tools: net worth, its series, accounts, account history, runway
Status: todo
Wave: 9   Lane: T
Touches: none
Blocked by: 083
Read first: docs/ADVISOR.md#tool-catalog, docs/ADVISOR.md#scope, docs/ARCHITECTURE.md#users-and-ownership

## Goal
The advisor can read every balance figure the dashboard shows, in either scope, with staleness
attached — through the same services the dashboard calls.

## Acceptance criteria
- [ ] `get_net_worth`, `get_net_worth_series`, `list_accounts`, `get_account_history`, `get_runway`,
      with the parameters, bounds and returns in ADVISOR.md#tool-catalog, each passing `today` from
      the context to its service.
- [ ] Scope maps to the viewer exactly as `routers/net_worth._viewer` does: `mine` → the
      authenticated user's id, `household` → `None`. No tool accepts a user id.
- [ ] `get_runway`: scope changes liquid assets only. A test asserts the burn windows are identical
      in both scopes.
- [ ] `get_net_worth_series`: at most 120 points; `day` interval only for spans of 92 days or less;
      a `coverage` block giving the earliest snapshot and saying when points before it were
      omitted.
- [ ] `get_account_history`: snapshots downsampled to month-ends past 120 points; every stake row.
- [ ] Staleness everywhere: per-account `stale` flags, `stale_accounts` in the envelope.
- [ ] Runway months render at one decimal through `render.py`. The service's `float` is converted
      via `Decimal(str(value))` and never used arithmetically.
- [ ] Tests: each tool against its service on synthetic fixtures with hand-computed values —
      including the 50%-owned rental in both scopes, a stake change mid-series, a closed account,
      and a balance stale by 91 days; out-of-bounds arguments return `invalid_args`.

## Files
- `api/app/advisor/tools/balances.py` (new)
- `api/tests/test_advisor_tools_balances.py`

## Notes
Lane T owns `advisor/tools/{balances,spending,cards}.py` and nothing else. If a tool needs a
service that does not exist, that is lane S's or 082's work, not a reason to query from here.
