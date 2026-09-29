# 103 — Privacy hardening: Sentry, logs, and a demo that cannot hold a key
Status: done
Wave: 10   Lane: L
Touches: none
Blocked by: 097
Read first: docs/ADVISOR.md#audit-and-observability, docs/ADVISOR.md#demo, docs/adr/0014-the-demo-advisor-replays-recorded-answers.md

## Goal
Nothing the advisor reads can leave through an error report or a log line, and the public demo is
structurally unable to call a model. A gate for switching the advisor on.

## Acceptance criteria
- [x] `observability.py` sets `include_local_variables=False`. It defaults to on, and a stack
      frame in the loop holds prompts and tool results; `before_send` redacts monetary *keys*, not
      "$1,234.56" inside a string. This also closes the same gap for the rest of the API.
- [x] A test raises inside a tool whose result holds a dollar figure and a merchant string, and
      asserts the captured event contains neither.
- [x] Advisor log lines carry turn id, tool name, status, latency and row count only. A test
      asserts arguments, results and question text never reach the log output.
- [x] `advisor_active` is false under `DEMO_MODE` whatever else is set — tested.
- [x] `scripts/check_no_model_key_outside_api.sh` fails if `ANTHROPIC` appears in `web/`,
      `fly.web.toml`, `fly.demo-api.toml` or `fly.demo-web.toml`, with comments stripped first (the
      lesson from the demo guard, whose own explanation once matched its grep). Wired into
      `make guards` and CI, with a self-test in `test_guards.sh`.
- [x] Tests: as above, plus the guard's self-test fails on a planted key reference and passes on
      the clean tree.

## Files
- `api/app/observability.py`
- `scripts/check_no_model_key_outside_api.sh` (new), `scripts/test_guards.sh`
- `.github/workflows/ci.yml`, `Makefile`
- `api/tests/test_advisor_privacy.py`

## Done — 2026-09-28

- `include_local_variables=False`, with a control test showing the same frame **does** leak
  with it on — so the test measures what it claims.
- **Found: Postgres quotes data in its own error text** — `invalid input syntax …: "$1,234.56"`,
  `Failing row contains (…)` — which `hide_parameters` cannot reach. So `_scrub` now withholds
  every exception's message in an error report (type and stack stay), for the whole API, and
  the engine sets `hide_parameters=True` for SQLAlchemy's own `[parameters: …]` block.
- The loop and the registry catch their exceptions, so Sentry would never see an advisor
  failure. `report_advisor_failure` sends one message per failure with where, the error class
  and ids as tags — no exception object, no stack.
- The loop logs `advisor_tool_call` (turn, tool, status, latency, rows) and
  `advisor_turn_finished` (turn, status, grounding, count). A test records every advisor log
  call through a real turn and checks the fields against an allowlist and for the question,
  an argument and a result.
- `check_no_model_key_outside_api.sh` matches `ANTHROPIC` and `@anthropic-ai/` after stripping
  comments (keeping `https://`), skips Markdown, and prints file and line numbers only — never
  the matching line, which could be a key. Five self-tests, including one on this repository.
