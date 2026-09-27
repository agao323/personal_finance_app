# 096 — The model client, the price table, and the advisor's settings
Status: todo
Wave: 10   Lane: L
Touches: **dependency** (`anthropic`, pinned)
Blocked by: 081
Read first: docs/ADVISOR.md#model-configuration, docs/ADVISOR.md#cost, docs/adr/0009-advisor-model-provider.md, docs/adr/0010-the-advisor-loop-runs-in-the-api.md

## Goal
A provider-neutral `ModelClient` with two implementations — Anthropic's API and a scripted fake —
and an effective-dated price table, so the loop can be written and tested with no network and no
key.

## Acceptance criteria
- [ ] `anthropic` added to `api/pyproject.toml` at an **exact** version, `uv.lock` committed. The
      Python SDK has a 0.x → 1.x major in flight; upgrades are deliberate.
- [ ] Settings: `advisor_enabled` (default **false**), `anthropic_api_key` (secret, optional),
      `advisor_model` (`claude-opus-5`), `advisor_effort` (`medium`), `advisor_max_tokens` (6000),
      and the three caps in cents. An `advisor_active` property is true only when enabled, a key is
      present, **and** `demo_mode` is false.
- [ ] `advisor/model.py`: the `ModelClient` protocol — stream a request, yield text deltas and
      complete `tool_use` blocks, end with the stop reason, usage, served model, request id and the
      full content blocks.
- [ ] `AnthropicModelClient` builds the request exactly as ADVISOR.md#model-configuration says:
      adaptive thinking, effort, strict tools **sorted by name**, a cache breakpoint on the last
      static system block plus top-level automatic caching, `fallbacks: "default"` with its beta
      header, **no** `eager_input_streaming`, **no** server tools.
- [ ] `ScriptedModelClient` replays a script — text chunks, tool calls, stop reasons, usage — and
      can assert on each request it receives (for instance, that tool results came back).
- [ ] `advisor/pricing.py`: per-MTok `Decimal` prices for input, 5-minute write, 1-hour write,
      cache read and output, effective-dated, for `claude-opus-5`, `claude-sonnet-5`,
      `claude-opus-4-8` and `claude-haiku-4-5` as verified on 2026-09-27. `cost(usage, model)` at
      full precision; one `display_cents` that rounds once. An unknown model costs as the most
      expensive known one.
- [ ] Tests: the request body captured through an `httpx.MockTransport` passed to the SDK client —
      no network — and asserted field by field; the scripted client; pricing against hand-computed
      examples covering every token class; the configured default model has a price.

## Files
- `api/pyproject.toml`, `api/uv.lock`
- `api/app/config.py`
- `api/app/advisor/model.py` (new)
- `api/app/advisor/pricing.py` (new)
- `api/tests/test_advisor_model.py`

## Notes
Verify the SDK surface against the installed version rather than memory: the beta messages path
for `fallbacks`, the streaming helper, and how `usage` reports cache writes by TTL. Write the test
first and let it show what the SDK actually sends.

Mid-conversation system messages (used for the per-turn context and the grounding retry) are
supported on Opus 5 and not on Sonnet 5. The client needs a capability flag per model so the loop
can prepend the context to the user turn instead.
