# 081 — The advisor and Insights contract, frozen
Status: done
Wave: 9   Lane: —
Touches: **contract**
Blocked by: none — 122's decisions are made. Conversations are private to each person, so
`ConversationSummary` needs no author field.
Read first: docs/ADVISOR.md#request-path, docs/ADVISOR.md#findings, docs/adr/0006-contract-changes-during-wave-2.md

## Goal
Every route and response model the Insights panel and the advisor will need is declared, stubbed at
`501`, and generated into `api-types.ts`. The tools, loop and web lanes then build against one
frozen contract, the way ticket 012 let Wave 2 run three lanes at once.

## Acceptance criteria
- [x] `schemas/advisor.py` declares the Insights models: `Finding`, `Evidence`, `FindingAction`,
      `InsightsRead`, and the enums `FindingKind`, `Severity`, `EvidenceUnit`, `ActionKind`,
      `Screen`. **`FindingKind` and `LimitationKind` ship complete** — every kind planned for
      Waves 9–12 — so later waves add findings without a contract change, as `enums.py` does.
      `LimitationKind` includes `market_data`.
- [x] …and the advisor models: `AdvisorStatus` (enabled, refusal reason, month spent and cap in
      cents, model), `ConversationCreate` (scope), `ConversationSummary`, `ConversationDetail`
      (turns with question, answer, figure checks, citations, **lookups**, limitations, policy
      notes, feedback, status), `TurnCreate` (question, 1–2,000 characters), `TurnFeedback`
      (`good` or `flagged`, note ≤ 500), `Citation`, `Lookup` (tool, arguments summary, rows,
      latency, as-of), and **`AdvisorEvent`** — a discriminated union of `turn_started`,
      `tool_call`, `text_delta`, `answer`, `regenerating`, `error`, `heartbeat`, `turn_complete`.
- [x] `FigureCheck` carries a span, a status — `verified` (a resolved reference), `matched` (a bare
      number found in a tool result) or `unverified` — and, when known, its **source**: call id and
      path. This is the Proof-Carrying Numbers shape in ADVISOR.md#grounding.
- [x] Routes, all `501`: `GET /insights`; `GET /advisor/status`; `GET POST /advisor/conversations`;
      `GET DELETE /advisor/conversations/{conversation_id}`;
      `POST /advisor/conversations/{conversation_id}/turns` (declared `text/event-stream`);
      `PUT /advisor/turns/{turn_id}/feedback`; `GET /advisor/stream-check`.
- [x] `AdvisorEvent` appears under `components` in `api-types.ts` although it is only ever sent as
      SSE. If `openapi-typescript` does not emit it from the route's `responses`, fix
      `scripts/export_openapi.py` — never hand-edit the generated file.
- [x] ARCHITECTURE.md's endpoint table lists each new route against its implementing ticket; the
      inventory test enforces it.
- [x] Money is `*_cents`, percentages `*_bps`, other ratios fixed-point with the scale in the name.
      A test walks every advisor schema and fails on a `float`.
- [x] `make types` run and committed.
- [x] Tests: contract test — each route exists and returns `501`, each schema name is in
      `openapi.json`, the event union's discriminator values are exactly the eight above; the
      float walk.

## Files
- `api/app/schemas/advisor.py` (new)
- `api/app/routers/advisor.py`, `api/app/routers/insights.py` (new, stubs)
- `api/app/main.py`
- `docs/ARCHITECTURE.md`
- `web/src/lib/api-types.ts` (generated)

## Notes
After this lands, the ADR 0006 procedure applies: a ticket that needs a shape changed **stops**,
the change is made additively in a re-freeze commit, and the ticket resumes. Lane W starts the
moment this merges; it builds against MSW handlers typed from this file.

`Screen` is the enum of in-app destinations a finding action or an answer's screen token may point
at. Routes are mapped from it in exactly one web function; nothing in the contract is a URL.

Titles on findings are server-rendered from templates and evidence. Declare `title` as a plain
string; the web renders it as text, never as markdown.

## Done — 2026-09-27

- **`view`, not `scope`.** `ConversationCreate`, `InsightsRead` and `Citation` name the Mine /
  Household field `view`, matching `NetWorthRead` and every existing `?view=` query. Two names
  for one concept in one contract is how a client ends up sending the wrong one.
- **`EventStreamResponse`** — a `StreamingResponse` subclass with `media_type =
  "text/event-stream"` — is the turn route's `response_class`. Without it FastAPI files the event
  model under `application/json`, which the route never sends. FastAPI still adds a stray
  `type: string` beside the `$ref`; harmless, because the web reads
  `components["schemas"]["AdvisorEvent"]` directly rather than the operation's response type.
- **`test_integration.py` gained a `PENDING` map.** Its completeness check asserted that no route
  answers 501, which was true once Wave 2 closed and is deliberately false during a freeze. Each
  implementing ticket deletes its line, and the test fails both for an unlisted stub and for a
  line left behind after its route went live.
- `ErrorEvent.resets_on`, `AdvisorStatus.resets_on` and `TurnCompleteEvent.month_spent_cents`
  were added while writing the shapes the chat will need to explain a refusal — they are the
  "until when" and "how much so far" of a cap message.
