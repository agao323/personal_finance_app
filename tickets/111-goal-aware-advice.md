# 111 — Goal-aware advice: progress, findings, tools, evals
Status: todo — order provisional
Wave: 11   Lane: —
Touches: none (`GoalRead.progress` and the goal finding kinds were declared in 108 and 081)
Blocked by: 101, 108, 109
Read first: docs/ADVISOR.md#findings, docs/ADVISOR.md#advice-guardrails, docs/ADVISOR.md#evals

## Goal
"Am I on track?" has a computed answer for every goal, the Insights panel says when one is off
track, and the advisor recommends against the household's own targets and stated assumptions
instead of defaults.

## Acceptance criteria
- [ ] `services/analysis/goals.py`: progress per kind — spending limit (month to date and last
      complete month against the limit, via `spend.spend_totals`); emergency fund (6-month runway
      against target months); savings target (linked accounts' ownership-adjusted balances in the
      goal's scope, against the target, and the monthly amount still needed by the date, rounded
      once in `numbers.py`) — with `on_track`.
- [ ] `GoalRead.progress` filled.
- [ ] Findings `goal_off_track`, `spending_limit_exceeded`, `emergency_fund_below_target`; the last
      **replaces** `runway_low`'s default threshold whenever an emergency-fund goal exists.
- [ ] Tools `list_goals`, `evaluate_goals(goal_id?)`, `get_planning_profile` — the profile tool
      returns assumptions with a `defaults: true` flag when nobody has set them.
- [ ] System prompt addition: use goals and stated assumptions; name them when used.
- [ ] Six goal-aware eval cases with the advice rubric.
- [ ] Tests: hand-computed progress for each kind, including a savings target with a 50%-owned
      account in both scopes, and a spending limit exceeded mid-month.

## Files
- `api/app/services/analysis/goals.py` (new)
- `api/app/services/findings.py`
- `api/app/advisor/tools/goals.py` (new)
- `api/app/routers/goals.py`
- `api/evals/cases/goals.yaml` (new)
- `api/tests/test_analysis_goals.py`
