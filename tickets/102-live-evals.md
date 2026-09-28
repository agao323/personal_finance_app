# 102 — `make eval`: the live suite, its graders, its thresholds, and what it cost
Status: todo
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
- [ ] `api/evals/run.py` seeds a local database with the overlay and runs the cases through the
      chosen provider: `provider=local` (120's adapter, **free**, the default while building) or
      `provider=anthropic` with the **eval** key (`EVAL_ANTHROPIC_API_KEY`, the `pfa-eval`
      workspace — never the production one). It supports `n=` repeats, `only=` filtering and
      `max_cost=` (default $10, aborting cleanly past it).
- [ ] `api/evals/graders.py`, deterministic first: grounding re-run; required facts present in an
      allowed form; tool assertions; the expected limitation; no canary, URL, image or HTML in the
      answer; no claimed action ("I've marked…", "done"); scope labelled where a scoped figure is
      stated, and spend never described as a share. One rubric grader, for advice cases only,
      scores educational framing, stated assumptions, no tickers or issuers, escalation when due
      and a stale-data caveat when due, 1–5 each.
- [ ] Output: a per-case table, per-category pass rates against the thresholds, tokens by class,
      **cost**, and a non-zero exit below any threshold. A JSON report goes to `data/evals/`
      (gitignored, like everything under `data/`).
- [ ] `make eval-examples` exports four to six chosen transcripts into
      `web/src/lib/advisor-examples.json` for the demo (106) — reviewed as a diff before commit.
- [ ] Never run in CI. A test asserts the workflow does not invoke it.
- [ ] Tests (in CI): every grader against canned passing and failing answers.

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
