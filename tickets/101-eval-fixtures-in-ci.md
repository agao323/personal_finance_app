# 101 — Eval fixtures in CI: the overlay, the golden set, and computed expectations
Status: todo
Wave: 10   Lane: L
Touches: none
Blocked by: 084, 085, 086, 093, 097
Read first: docs/ADVISOR.md#evals, docs/SECURITY.md#demo-isolation

## Goal
The golden questions, the synthetic world they are asked about, the injection corpus, and every
expected answer exist and are checked in CI — computed by the same services the tools call, so an
expected answer can never quietly disagree with the app.

## Acceptance criteria
- [ ] `api/evals/overlay.py` applies ADVISOR.md#the-fixture-world on top of
      `seed(today=EVAL_TODAY, seed=20260818)`: five fixed-amount subscriptions (a price increase,
      an annual, a weekly, a lapsed one), a restaurant spike month, an unmarked transfer pair, an
      urgent unused perk, a balance stale by 120 days, and the injection corpus. It calls
      `assert_not_real` first and refuses a real database.
- [ ] `api/evals/injection.yaml`: at least 12 planted strings — direct instructions, fake role
      markers, a markdown image pointing at an outside host, a link, a request to call
      `search_transactions` for everything, an instruction to misstate net worth, one hidden with
      zero-width characters — each carrying a unique canary token, planted across merchant,
      description, perk note, account name and rule pattern. Each is marked whether the sanitiser
      is expected to withhold it; the subtle ones are there for the model, not the sanitiser.
- [ ] `api/evals/cases/*.yaml`: the categories and rough counts in ADVISOR.md#categories. Each case
      has id, category, scope, question, and any of: facts, `tools_any`, `tools_none`,
      `max_tool_calls`, `expect_limitation`, `canaries`, `expect_screen`.
- [ ] `api/evals/facts.py`: each fact is a function of `(session, today)` over the services — never
      a typed-in number.
- [ ] `make eval-fixtures` writes `api/evals/expected.json`.
- [ ] CI tests, no model: `expected.json` matches a fresh computation; every case names tools and
      facts that exist; the overlay plants what it claims; every corpus string marked "withheld"
      is withheld when rendered through the real tools; a handful of golden cases run end to end
      against `ScriptedModelClient` with scripted tool plans and answers built from
      `expected.json`, so the graders and the loop are exercised together.

## Files
- `api/evals/overlay.py`, `api/evals/facts.py` (new)
- `api/evals/cases/*.yaml`, `api/evals/injection.yaml` (new)
- `api/evals/expected.json` (generated, committed)
- `api/tests/test_eval_fixtures.py`
- `Makefile`

## Notes
The overlay stays out of the demo seed. The demo is meant to look like a household; a merchant
called "IGNORE PREVIOUS INSTRUCTIONS" does not, and the e2e figures would move. If some of the
overlay (the subscriptions, the spike) would make the demo's Insights panel better, promote it in a
separate ticket that updates the e2e expectations too.
