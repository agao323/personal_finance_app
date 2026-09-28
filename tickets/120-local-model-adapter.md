# 120 — A local model for development and evals, so building the advisor costs nothing
Status: todo
Wave: 10   Lane: L
Touches: none
Blocked by: 096
Integrates with: 102
Read first: docs/adr/0009-advisor-model-provider.md, docs/ADVISOR.md#the-loop, docs/ADVISOR.md#evals

## Goal
The advisor runs end to end on a laptop against a free open-weight model and the synthetic seed, so
every Wave 10 ticket can be built and tried without an API key or a bill. Money is first spent when
the owner switches the advisor on in production (107), and not before.

## Acceptance criteria
- [ ] `LocalModelClient` implements the `ModelClient` protocol against a local model server's
      OpenAI-compatible chat endpoint (Ollama by default), over `httpx`. It translates the stored
      Anthropic-shaped content blocks to chat messages and back: `tool_use` ↔ `tool_calls`,
      `tool_result` ↔ `role: tool`. Text streams; tool calls are accumulated before they are
      returned.
- [ ] Settings: `advisor_provider` (`anthropic` · `local` · `scripted`), `local_model_url`,
      `local_model`. **The local provider is refused whenever `is_deployment` is true**, at startup
      and per request. Production can never be pointed at a laptop, which is ADR 0009's network
      argument enforced in code rather than remembered.
- [ ] The capability flag from 096 reports no mid-conversation system messages for the local
      provider, so the per-turn context is prepended to the user turn.
- [ ] Usage is recorded in token counts as for any provider, and priced at **$0** through a `local`
      entry in the price table, so caps and reports work unchanged.
- [ ] The compose override points the API container at the host's model server
      (`http://host.docker.internal:11434`). The model runs on the Mac itself, because containers on
      macOS cannot use its GPU.
- [ ] `make advisor-local` prints the setup — install Ollama, pull the default model (about 13 GB;
      the owner runs the download) — and checks the server answers before starting the stack.
- [ ] Tests, no network: request and response translation against recorded chat-completions
      payloads, including a turn with two parallel tool calls and a malformed tool call that must come
      back as `invalid_args`; the deployment refusal.

## Files
- `api/app/advisor/model_local.py` (new)
- `api/app/config.py`, `api/app/advisor/pricing.py`
- `docker-compose.override.yml`, `Makefile`
- `api/tests/test_advisor_model_local.py`

## Notes
**The default model is `gpt-oss:20b`** (about 16 GB, fits the 48 GB M4 Pro with room to spare). A
Qwen-class 30B mixture-of-experts model is the alternative. Check the current tags when this is
picked up, and let `make eval provider=local` choose between them rather than a leaderboard.

Expect a local model to be weaker at multi-step plans than the hosted one. The design already
compensates: analyses compute, the findings engine decides what matters, and grounding rejects
invented figures. A local model mostly has to choose tools and explain results. How well it does
that on *these* questions is exactly what the eval run measures, and it is the evidence ADR 0009's
first revisit condition asks for.

Development databases hold synthetic data only (SECURITY.md), so nothing real reaches the local
model. Running it over a restored copy of real data would be free and self-contained, and it would
also break that rule; that is a separate decision, not something this ticket enables.
