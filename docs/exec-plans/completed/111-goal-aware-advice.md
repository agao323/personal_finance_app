# 111 — Goal-aware advice: progress, findings, tools, evals
Status: done
Wave: 11   Lane: —
Touches: none (`GoalRead.progress` and the goal finding kinds were declared in 108 and 081)
Blocked by: 101, 108, 109
Read first: docs/ADVISOR.md#findings, docs/ADVISOR.md#advice-guardrails, docs/ADVISOR.md#evals

## Goal
"Am I on track?" has a computed answer for every goal, the Insights panel says when one is off
track, and the advisor recommends against the household's own targets and stated assumptions
instead of defaults.

## Acceptance criteria
- [x] `services/analysis/goals.py`: progress per kind — spending limit (month to date and last
      complete month against the limit, via `spend.spend_totals`); emergency fund (6-month runway
      against target months); savings target (linked accounts' ownership-adjusted balances in the
      goal's scope, against the target, and the monthly amount still needed by the date, rounded
      once in `numbers.py`) — with `on_track`.
- [x] `GoalRead.progress` filled.
- [x] Findings `goal_off_track`, `spending_limit_exceeded`, `emergency_fund_below_target`; the last
      **replaces** `runway_low`'s default threshold whenever an emergency-fund goal exists.
- [x] Tools `goals_list`, `goals_evaluate(goal_id?)`, `planning_profile` — the profile tool
      returns assumptions with a `defaults: true` flag when nobody has set them.
- [x] System prompt addition: use goals and stated assumptions; name them when used.
- [x] Six goal-aware eval cases with the advice rubric.
- [x] Tests: hand-computed progress for each kind, including a savings target with a 50%-owned
      account in both scopes, and a spending limit exceeded mid-month.

## Files
- `api/app/services/analysis/goals.py` (new)
- `api/app/services/findings.py`
- `api/app/advisor/tools/goals.py` (new)
- `api/app/routers/goals.py`
- `api/evals/cases/goals.yaml` (new)
- `api/tests/test_analysis_goals.py`

## Done — 2026-09-28

- **Each goal is measured in its own scope** — a household goal counts every stake, a personal
  goal its owner's — whoever asks. A test holds a 50/50 joint account: $10,000 saved for the
  household goal, $5,000 for the owner's.
- Spending limits are on track at or under the pro-rata share of the month (spent × days ≤
  limit × day-of-month, integers only); a parent category counts its children. Emergency funds
  use the six-month burn window. Savings targets are on track at or above the straight line
  from the goal's creation to its date; the monthly amount still needed rounds once, half up.
- Findings: `spending_limit_exceeded` (warning) once over the limit, `goal_off_track` (notice)
  for a limit on pace to pass or a savings target behind its line, and
  `emergency_fund_below_target` (warning), which **replaces `runway_low` whenever an active
  emergency-fund goal exists** — tested both ways, including archiving the goal.
- Tools `goals_list`, `goals_evaluate(goal_id?)` and `planning_profile`, whose assumptions
  carry `defaults: true` until someone sets them. Another member's personal goal is not visible
  and evaluates as `invalid_args`.
- The system prompt gains "Goals and assumptions": measure against the household's goals, name
  the goal and the assumptions used, and say when the assumptions are the defaults.
- The eval world gains three goals, `expected.json` five goal facts (the 32 before are
  unchanged), and six active goal-aware cases; the Wave 12 advice cases moved to
  `cases/planned.yaml`, pending on 115, 116 and 118.
- `make eval-fixtures` now builds in `pfa_eval`, created and migrated on demand
  (`evals/database.py`), instead of borrowing the development database — which was a schema
  behind and lacked the goal tables. `make eval` shares the same module.
