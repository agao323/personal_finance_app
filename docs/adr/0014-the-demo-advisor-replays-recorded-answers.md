# ADR 0014 — The demo's advisor replays recorded answers; it never calls a model

Status: proposed · 2026-09-27 · Ticket 080

## Context

The demo ([ADR 0003](0003-demo-isolation.md)) is public, unauthenticated, indexed, and edge-cached,
over a synthetic dataset. The advisor is the most interesting thing the project will have built,
and every question asked of it costs money.

## Decision

**No model on the demo.**

- `advisor_enabled` is false whenever `DEMO_MODE` is set, whatever else is configured. The demo
  deployment holds no model key, and a CI guard fails if `ANTHROPIC` appears in `web/`,
  `fly.web.toml` or either demo config.
- The demo's advisor screen replays a handful of **recorded example conversations**, produced by
  `make eval` against the synthetic seed, reviewed, and committed. They are synthetic by
  construction.
- The **Insights panel runs live** on the demo. It is deterministic, calls no model, and caches
  at the edge like everything else there.

## Alternatives considered

**A live endpoint, rate-limited.** Shows the real thing. It is also a public, unauthenticated way
to spend the owner's money: per-IP limits are routed around, a Cloudflare rate-limit rule bounds
requests rather than tokens, and a household-wide monthly cap would let one visitor exhaust the
real app's month. It would also need somewhere to keep rate-limit state, and this app has no cache
or queue by design. The demo is also read-only by middleware, and a turn is a POST.

**Disabled entirely.** The simplest option, and it hides the feature most worth showing.

**A separate low-cost model and key for the demo.** Smaller spend, same exposure: still a public
prompt surface, still money.

## Consequences

**Easy.** Zero cost, zero abuse surface, and the recordings double as a regression artefact: when
a model or prompt change moves an answer, the diff shows up in review.

**Hard.** The recordings go stale when the prompt or model changes, and have to be regenerated as
part of the release gate. A visitor cannot ask their own question; the screen says so plainly
rather than pretending.
