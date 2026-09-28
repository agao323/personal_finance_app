# ADR 0009 — The advisor's model is Anthropic's API, behind a seam that could take another

Status: proposed · 2026-09-27 · Ticket 080

## Context

The advisor ([docs/ADVISOR.md](../ADVISOR.md)) needs a model that can pick tools, read their
results and explain them. Whatever runs that model reads the household's finances: aggregates by
default, some transaction rows, account and merchant names.

During planning the owner asked the right question — *this information is so sensitive; can the
model be self-hosted and self-contained?* — and a follow-up that shaped the answer: *how would
production even reach a model on my Mac?* This records what was found on 27 September 2026.

**Where the data already goes.** Neon stores all of it. Fly runs the code that reads all of it.
Cloudflare terminates TLS in front of every response. A model provider would be a fourth
processor — and the first whose job is to *read* the content rather than store or carry it.
That difference is real, and it is also bounded: the choice is not "cloud or no cloud".

**What the provider's terms say** (Anthropic privacy centre, checked that day): commercial API
inputs and outputs are deleted within 30 days; inputs flagged for a usage-policy violation may be
kept up to two years; API data is not used for training by default. Zero data retention exists by
agreement.

**What self-hosting would take.**

- **Fly retired its GPU machines on 1 August 2026.** Every A10, L40S and A100 machine is gone.
  Inside Fly, a model now means CPU inference.
- The open-weight models that rank alongside frontier models on tool-use benchmarks (GLM-5.x,
  MiniMax M3, Kimi K2, DeepSeek V4) need roughly 75–128 GB of accelerator memory or several GPUs.
- The models that fit the owner's 48 GB M4 Pro MacBook — gpt-oss-20b in about 16 GB, Qwen3-class
  30B mixture-of-experts models in about 20 GB — form tool calls reliably in published community
  tests, and are weaker exactly where this app would lean on them: sequential, multi-step plans.
  Ollama, MLX and llama.cpp serve them behind an OpenAI-compatible endpoint.

## Decision

**Use the Anthropic API — `claude-opus-5` by default — through a provider-neutral `ModelClient`
protocol, and minimise what is sent.**

- The key lives only on pfa-api, in a dedicated `pfa-prod` Console workspace with a provider-side
  spend limit. Evals use a separate `pfa-eval` workspace and key.
- Aggregates by default; rows bounded and truncated; names sanitised; no email addresses, display
  names or institution names ([ADVISOR.md#provider-data-handling](../ADVISOR.md#provider-data-handling)).
- Nothing about the tools, the findings engine, the grounding check or the evals knows which
  provider is behind the seam. Swapping means one adapter and one `make eval` run.
- **Development and evals default to a free local model** (ticket 120): an open-weight model on
  the owner's Mac, reached by the local stack, against the synthetic seed. That is the laptop
  option without the objections below. Nothing is on Fly's private network, nothing needs to be
  awake for a phone, and nothing real is read. The local provider is refused on any deployment.
  **The hosted API is first used, and first paid for, when 107 switches the advisor on in
  production.**

## Alternatives considered

**A model on the owner's Mac, reached from Fly over WireGuard.** The Mac dials out — as a Fly
WireGuard peer or over Tailscale — so the home router opens no port, and pfa-api calls the model
over the tunnel. It is the only option that adds no third party. Rejected on two grounds.
Availability: the app is used from a phone, and the advisor would be down whenever a laptop is
asleep, closed or travelling. And security, which is the stronger reason: a peer on Fly's private
network can reach **pfa-api directly**, and "the API has no public address" is one of the
boundaries [ARCHITECTURE](../ARCHITECTURE.md#request-path) is built on. The API would still
verify the Access JWT, but that check exists as defence in depth, not as the boundary. Joining a
laptop to production's private network would turn it into the boundary.

A variant avoids the network join: a worker on the Mac *pulls* model jobs from the public origin
with a Cloudflare Access service token. It works, and it is a job queue, which PRODUCT rules out
for this app.

**An always-on home machine** (a 64 GB Mac mini, about $2,000). Fixes availability, not the
network argument above. It costs about eight years of the capped API budget.

**CPU inference on a Fly machine in the same organisation.** Same trust boundary as today, no new
processor. Rejected for now on latency and cost: our prompts are around 10K tokens, and a 20B-class
model prefilling that on CPU, several times per question, runs to minutes per answer (an estimate,
to be measured if this is revisited). An always-on performance machine large enough costs more per
month than the whole API budget. A `.internal` app cannot be woken by the Fly proxy either — the
same constraint `fly.api.toml` documents.

**A rented GPU** (Modal, RunPod, Lambda and similar). Still a third party processing plaintext,
under infrastructure terms that say less about retention than a model provider's — and this app
would then operate the serving stack too. No privacy gain over the API, more to run.

**Fly GPUs.** Retired.

## Consequences

**Easy.** The strongest tool use and reasoning available in production, no hardware, pay per
question, a hard provider-side spend limit. Building it costs nothing, because development runs on
the local model. The evals measure quality instead of assuming it.

**Hard.** A fourth processor reads household data, with 30-day retention and up to two years if
something is flagged. The advisor depends on a vendor's model lifecycle: models retire and SDKs
change majors. Pinning the model and SDK, and gating any change on a passing `make eval`, is the
mitigation.

**The seam has a cost that should be stated.** Stored history is Anthropic-shaped content blocks,
thinking blocks included. A different provider needs a translation layer and loses those
conversations' replay. Cheap to accept today; worth knowing before switching.

**Revisit when** any of these becomes true:

1. An open-weight model passes the [eval thresholds](../ADVISOR.md#pass-thresholds) on hardware
   the household would run always-on — measured, not read from a leaderboard. Ticket 120 makes
   this free to measure: `make eval provider=local` runs the same suite against the laptop's
   model.
2. Anthropic's retention or training terms change for the worse.
3. GPUs become available inside the Fly organisation again, or the app moves to a host that has
   them.
4. The owner decides a fourth processor is not acceptable at any price, in which case the
   always-on box with a pull-based worker is the design to reopen, queue and all.
