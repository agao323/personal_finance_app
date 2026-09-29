# 084 — Balance tools: net worth, its series, accounts, account history, runway
Status: done
Wave: 9   Lane: T
Touches: none
Blocked by: 083
Read first: docs/ADVISOR.md#tool-catalog, docs/ADVISOR.md#scope, docs/ARCHITECTURE.md#users-and-ownership

## Goal
The advisor can read every balance figure the dashboard shows, in either scope, with staleness
attached — through the same services the dashboard calls.

## Acceptance criteria
- [x] `networth_get`, `networth_series`, `accounts_list`, `accounts_history`, `runway_get`,
      with the parameters, bounds and returns in ADVISOR.md#tool-catalog, each passing `today` from
      the context to its service.
- [x] Scope maps to the viewer exactly as `routers/net_worth._viewer` does: `mine` → the
      authenticated user's id, `household` → `None`. No tool accepts a user id.
- [x] `runway_get`: scope changes liquid assets only. A test asserts the burn windows are identical
      in both scopes.
- [x] `networth_series`: at most 120 points; `day` interval only for spans of 92 days or less;
      a `coverage` block giving the earliest snapshot and saying when points before it were
      omitted.
- [x] `accounts_history`: snapshots downsampled to month-ends past 120 points; every stake row.
- [x] Staleness everywhere: per-account `stale` flags, `stale_accounts` in the envelope.
- [x] Runway months render at one decimal through `render.py`. The service's `float` is converted
      via `Decimal(str(value))` and never used arithmetically.
- [x] Tests: each tool against its service on synthetic fixtures with hand-computed values —
      including the 50%-owned rental in both scopes, a stake change mid-series, a closed account,
      and a balance stale by 91 days; out-of-bounds arguments return `invalid_args`.

## Files
- `api/app/advisor/tools/balances.py` (new)
- `api/tests/test_advisor_tools_balances.py`

## Notes
Lane T owns `advisor/tools/{balances,spending,cards}.py` and nothing else. If a tool needs a
service that does not exist, that is lane S's or 082's work, not a reason to query from here.

## Done — 2026-09-27

- Account and share figures are named `balance` (the full account value) and `share` (after
  the stake), because "adjusted" is this codebase's word and not one a person asks about.
- **No names and no user ids for stake holders.** `accounts_history` reports a stake's owner as
  "you" or "another household member". The model needs to know whose share it is and nothing
  more about who holds it; a test asserts the partner's name never appears.
- `networth_get` defaults to `detail: full` — about ten accounts is a kilobyte, and "why" questions
  need the breakdown. `concise` drops it.
- The series refuses more than 120 points before calling the service, from a point-count
  estimate per interval, so a model asking for ten years of days learns why rather than getting
  a truncated result.
- Runway months cross from the service's `float` through `Decimal(str(value))` to tenths, for
  display only, as the ticket required; the arithmetic stays in `services/runway.py`.
