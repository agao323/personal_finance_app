# 118 — FIRE and what-if tools, and their evals
Status: todo — order provisional
Wave: 12   Lane: —
Touches: none (limitation kinds declared in 081)
Blocked by: 102, 117
Read first: docs/ADVISOR.md#projections, docs/ADVISOR.md#advice-guardrails

## Goal
The advisor can answer retirement questions with the projection engine's band, and "what if we
saved $500 more a month" with two computed scenarios and a computed difference.

## Acceptance criteria
- [ ] Tool `project_retirement(scope, retire_year?, annual_spend_cents?)`: the band, the earliest
      90%-success year, the assumptions used, and the data gaps (unknown allocation, missing tax
      treatment).
- [ ] Tool `what_if(change, value)`, `change` from an enum — `extra_monthly_saving`,
      `spend_change_bps`, `retire_year_shift` — each bounded; returns base and scenario and the
      differences, computed here.
- [ ] System prompt addition: projections are ranges; never state a single retirement number; name
      the assumptions and their version; say what the model ignores (the 59½ rule, deductibility).
- [ ] Six FIRE eval cases: facts from the engine (band endpoints, earliest year), the rubric, and a
      grader that fails any answer stating one figure as "the number you need".
- [ ] Tests: tool bounds; `what_if` differences equal the engine run twice; a question asked with
      no tax treatment recorded produces the limitation rather than a projection.

## Files
- `api/app/advisor/tools/projections.py` (new)
- `api/app/advisor/prompts/system.md`
- `api/evals/cases/fire.yaml` (new)
- `api/evals/graders.py`
- `api/tests/test_advisor_tools_projections.py`
