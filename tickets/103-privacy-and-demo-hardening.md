# 103 — Privacy hardening: Sentry, logs, and a demo that cannot hold a key
Status: todo
Wave: 10   Lane: L
Touches: none
Blocked by: 097
Read first: docs/ADVISOR.md#audit-and-observability, docs/ADVISOR.md#demo, docs/adr/0014-the-demo-advisor-replays-recorded-answers.md

## Goal
Nothing the advisor reads can leave through an error report or a log line, and the public demo is
structurally unable to call a model. A gate for switching the advisor on.

## Acceptance criteria
- [ ] `observability.py` sets `include_local_variables=False`. It defaults to on, and a stack
      frame in the loop holds prompts and tool results; `before_send` redacts monetary *keys*, not
      "$1,234.56" inside a string. This also closes the same gap for the rest of the API.
- [ ] A test raises inside a tool whose result holds a dollar figure and a merchant string, and
      asserts the captured event contains neither.
- [ ] Advisor log lines carry turn id, tool name, status, latency and row count only. A test
      asserts arguments, results and question text never reach the log output.
- [ ] `advisor_active` is false under `DEMO_MODE` whatever else is set — tested.
- [ ] `scripts/check_no_model_key_outside_api.sh` fails if `ANTHROPIC` appears in `web/`,
      `fly.web.toml`, `fly.demo-api.toml` or `fly.demo-web.toml`, with comments stripped first (the
      lesson from the demo guard, whose own explanation once matched its grep). Wired into
      `make guards` and CI, with a self-test in `test_guards.sh`.
- [ ] Tests: as above, plus the guard's self-test fails on a planted key reference and passes on
      the clean tree.

## Files
- `api/app/observability.py`
- `scripts/check_no_model_key_outside_api.sh` (new), `scripts/test_guards.sh`
- `.github/workflows/ci.yml`, `Makefile`
- `api/tests/test_advisor_privacy.py`
