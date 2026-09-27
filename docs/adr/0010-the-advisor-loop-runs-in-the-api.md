# ADR 0010 — The advisor loop runs in pfa-api, hand-written, streamed over SSE

Status: proposed · 2026-09-27 · Ticket 080

## Context

An agent is a loop: send the conversation and the tool definitions to the model, run whatever
tools it asks for, send the results back, repeat until it answers. Somewhere has to own that
loop, and the choice decides where the API key lives, how tools reach the data, how the answer
reaches the browser, and what can be tested without a network.

Fixed constraints: the key exists only on pfa-api; the browser talks only to the Next.js origin;
every tool call is logged with its arguments; caps are checked before spend; the whole loop runs
in CI against a fake model.

## Decision

**A hand-written async loop in pfa-api**, over `AsyncAnthropic` streaming, behind a
`ModelClient` protocol with a scripted implementation for tests. Tools call services in-process.
The answer streams to the browser as **server-sent events over a POST**, through the existing
BFF proxy.

Three details that would otherwise read as mistakes:

- **Eager input streaming is off**, although the SDK's guidance turns it on for streaming client
  tools. It lets large tool inputs stream as they are generated, and in exchange the API stops
  validating them. Our inputs are a date range and an enum; the validation is worth more.
- **A turn is not one database transaction** — the one deliberate exception to
  [ADR 0005](0005-request-scoped-transactions.md). Each tool call gets its own read-only
  transaction and each persistence write its own short one, because a turn lasts up to two
  minutes and because audit rows must survive the failure they record.
- **Cancellation is forwarded.** `route.ts` passes the browser request's `signal` to the upstream
  fetch; the API watches for disconnect and closes the model stream, so a closed tab stops
  spending.

## Alternatives considered

**The loop in a Next.js route handler, with the TypeScript SDK.** Rejected outright: the model key
would live on pfa-web, the one publicly addressable app, and every tool would be an HTTP call back
into the API — the ownership and rounding rules re-reached through a network hop, from a language
without the services.

**The SDK's Tool Runner** (`client.beta.messages.tool_runner`). The strongest alternative: it owns
the loop and its per-turn hooks can intercept calls. It lost narrowly. It is beta; this loop needs
a budget check before every model call and tool call, an audit row per call, a grounding
regeneration that injects an operator message, cancellation, and a mapping to our own event
types. That is most of a hand-written loop expressed as hooks, and the fake model is simpler to
place at the client boundary than inside a runner. The hand-written loop is about 150 lines, owned
end to end, with no beta dependency.

**Managed Agents.** Anthropic runs the loop and hosts a sandbox. Our tools would still be custom
tools that round-trip to us, so the sandbox buys nothing for read-only queries, and sessions are
persisted provider-side, longer-lived than a request. More data at the provider for no capability
we need.

**WebSockets instead of SSE.** `route.ts` deliberately drops hop-by-hop headers, `upgrade`
included; a WebSocket would need a second proxy path through the BFF, Cloudflare Access and Fly.
One request streaming one answer is what SSE is for.

**Polling.** More requests, worse latency, and a job store. No.

## Consequences

**Easy.** The key never leaves pfa-api. Tools are ordinary Python calling ordinary services, tested
with pytest against the migrated database. The whole loop — tool round-trips, caps, regeneration,
refusals, truncation, cancellation — runs in CI with no network.

**Hard.** The loop is ours to maintain, including SDK upgrades (the Python SDK has a 0.x → 1.x
change in flight; pin it). Streaming adds failure modes the rest of the app does not have —
buffering by an intermediary, idle timeouts, disconnects — and ticket 100 has to prove the real
hops rather than assume them.

**The exception to ADR 0005 is scoped.** It applies to the streaming turn endpoint only. Every
other advisor route — listing and deleting conversations, status — is an ordinary request with an
ordinary request-scoped transaction.
