# 118 — FIRE and what-if tools, and their evals
Status: done
Wave: 12   Lane: —
Touches: none (limitation kinds declared in 081)
Blocked by: 102, 117
Read first: docs/ADVISOR.md#projections, docs/ADVISOR.md#advice-guardrails

## Goal
The advisor can answer retirement questions with the projection engine's band, and "what if we
saved $500 more a month" with two computed scenarios and a computed difference.

## Acceptance criteria
- [x] Tool `projection_retirement(scope, retire_year?, annual_spend_cents?)`: the band, the earliest
      90%-success year, the assumptions used, and the data gaps (unknown allocation, missing tax
      treatment).
- [x] Tool `projection_what_if(change, value)`, `change` from an enum — `extra_monthly_saving`,
      `spend_change_bps`, `retire_year_shift` — each bounded; returns base and scenario and the
      differences, computed here.
- [x] System prompt addition: projections are ranges; never state a single retirement number; name
      the assumptions and their version; say what the model ignores (the 59½ rule, deductibility).
- [x] Six FIRE eval cases: facts from the engine (band endpoints, earliest year), the rubric, and a
      grader that fails any answer stating one figure as "the number you need".
- [x] Tests: tool bounds; `projection_what_if` differences equal the engine run twice; a question asked with
      no tax treatment recorded produces the limitation rather than a projection.

## Files
- `api/app/advisor/tools/projections.py` (new)
- `api/app/advisor/prompts/system.md`
- `api/evals/cases/fire.yaml` (new)
- `api/evals/graders.py`
- `api/tests/test_advisor_tools_projections.py`

## Done — 2026-09-28

- `projection_retirement` returns the band — success by withdrawal rate at the target year and by
  retirement year, historical and shuffled, the earliest 90% year — with the buckets, spending,
  savings, tax rate, `assumptions_id`, the returns source and the data gaps: value with no
  allocation, 529 money, and accounts whose tax treatment was assumed from their type.
- When something is missing the result carries `unavailable` and the limitation kind to note, and
  no figures: no returns table or birth year (`projections`), no year of spending
  (`transaction_coverage`), no allocation entered (`holdings`), or **no tax treatment recorded on
  any portfolio account** (`tax_treatment`), which is how "asked with no tax treatment recorded"
  produces the limitation rather than a projection.
- `projection_what_if` runs the engine twice on the same seed, so the difference is the change's
  alone; a test holds each change's differences equal to the engine run twice by hand. Its result
  carries the two bands and one set of assumptions and limitations, to stay inside the result
  budget. Bounds: $10,000 a month, 50% of spending, 15 years, each way.
- The eval world projects on its own synthetic returns table, opted into through a context-scoped
  override in `evals` (`synthetic_returns()`); production refuses a synthetic table. The owner is
  born 1984 aiming for 2039. The seed now stores each account's default tax treatment, as the API
  does on create — without it every seeded account read as untreated.
- Six `fire` cases plus the now-active `goal-retirement`; six facts from the engine (the band's 3%,
  4% and 4.5% success, the earliest year, and the earliest year after each what-if). The grader
  fails any answer stating a single figure as "the number"; the existing 37 facts are unchanged.
- **Owner step:** the live run of these cases is part of `make eval provider=anthropic n=3`.
