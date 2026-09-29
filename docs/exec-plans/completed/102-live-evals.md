# 102 — `make eval`: the live suite, its graders, its thresholds, and what it cost
Status: done
Wave: 10   Lane: L
Touches: none
Blocked by: 098, 099, 101
Integrates with: 120
Read first: docs/ADVISOR.md#evals, docs/ADVISOR.md#pass-thresholds

## Goal
One command asks the golden questions of the real model against the synthetic world, grades every
answer, compares the results with the thresholds, and prints what it cost. It is the release gate
for switching the advisor on and for every later change of model, effort, prompt or tool.

## Acceptance criteria
- [x] `api/evals/run.py` seeds a local database with the overlay and runs the cases through the
      chosen provider: `provider=local` (120's adapter, **free**, the default while building) or
      `provider=anthropic` with the **eval** key (`EVAL_ANTHROPIC_API_KEY`, the `pfa-eval`
      workspace — never the production one). It supports `n=` repeats, `only=` filtering and
      `max_cost=` (default $10, aborting cleanly past it).
- [x] `api/evals/graders.py`, deterministic first: grounding re-run, reporting how many figures
      were verified references, matched bare numbers, or unverified; required facts present in an
      allowed form; tool assertions; the expected limitation; no canary, URL, image or HTML in the
      answer; and **098's `advisor/policy.py` checks, imported, not copied**. One rubric grader,
      for advice cases only, scores educational framing, stated assumptions, no tickers or issuers,
      escalation when due and a stale-data caveat when due, 1–5 each.
- [x] **Grader calibration.** `make eval-label` shows the owner recorded synthetic answers one at a
      time and stores a pass or fail label for each; the report prints the rubric grader's
      agreement with those labels, and advice-category results are marked untrusted below 90%
      agreement.
- [x] Output: a per-case table, per-category pass rates against the thresholds, tokens by class,
      **cost**, and a non-zero exit below any threshold. A JSON report goes to `data/evals/`
      (gitignored, like everything under `data/`).
- [x] `make eval-examples` exports four to six chosen transcripts into
      `web/src/lib/advisor-examples.json` for the demo (106) — reviewed as a diff before commit.
- [x] Never run in CI. A test asserts the workflow does not invoke it.
- [x] Tests (in CI): every grader against canned passing and failing answers.

## Files
- `api/evals/run.py` (new)
- `api/evals/graders.py` (new)
- `Makefile`
- `api/tests/test_eval_graders.py`

## Notes
A run of about 70 cases is roughly $7 at `n=1`. The eval workspace has its own provider-side spend
limit, so a runaway run cannot touch the household's month.

Record every gating run in ADVISOR.md#eval-runs: date, model and effort, prompt version, cases and
repeats, pass rates, ungrounded count, cost.

## Done — 2026-09-28

- **The world lives in its own database**, `pfa_eval` on the local Postgres: created if missing,
  migrated, advisor tables truncated and the world rebuilt on every run. The development
  database is never touched. Override with `EVAL_DATABASE_URL`.
- `provider=anthropic` reads **only** `EVAL_ANTHROPIC_API_KEY`; a test sets the production key
  and shows the runner refuses. `provider=local` loads 120's adapter and says so plainly until it
  exists.
- The run's own caps are the run's budget (`max_cost`); cost is checked before each case, so a
  run stops cleanly between cases, and the gate fails when it stopped early.
- The rubric grader goes through the same `ModelClient`, with no tools — `AnthropicModelClient`
  now leaves out `tools` and `tool_choice` for a request that has none. It scores the five
  criteria 1–5 and the reply must be exactly that JSON object.
- **Calibration re-grades every labelled answer on each run** and reports agreement; advice
  results are untrusted below 90% or with no labels. Labels live in `data/evals/labels.json`.
- The advice category is `goal_aware`, whose cases are all pending on 111–118, so the rubric has
  nothing to grade until then. The machinery is tested with a scripted grader.
- The median-cost threshold applies to paid providers only.
- `make eval-examples` exports passing runs of six chosen cases (four at least) to
  `web/src/lib/advisor-examples.json`, for 106.
- Not run here: `make eval` needs a model — the local one (120, a large download) or the eval
  key — both owner steps. Everything it runs is exercised in CI with the scripted model.
- Found and fixed on the way: `net_worth` listed accounts in table order (ticket 121), which made
  `test_net_worth_series.py` fail once the eval tests were in the suite.
