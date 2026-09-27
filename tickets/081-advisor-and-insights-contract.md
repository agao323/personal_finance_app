# 081 — The advisor and Insights contract, frozen
Status: todo
Wave: 9   Lane: —
Touches: **contract**
Blocked by: 080 (open decision 5 — whose conversations are visible — shapes the list route)
Read first: docs/ADVISOR.md#request-path, docs/ADVISOR.md#findings, docs/adr/0006-contract-changes-during-wave-2.md

## Goal
Every route and response model the Insights panel and the advisor will need is declared, stubbed at
`501`, and generated into `api-types.ts`. The tools, loop and web lanes then build against one
frozen contract, the way ticket 012 let Wave 2 run three lanes at once.

## Acceptance criteria
- [ ] `schemas/advisor.py` declares the Insights models: `Finding`, `Evidence`, `FindingAction`,
      `InsightsRead`, and the enums `FindingKind`, `Severity`, `EvidenceUnit`, `ActionKind`,
      `Screen`. **`FindingKind` and `LimitationKind` ship complete** — every kind planned for
      Waves 9–12 — so later waves add findings without a contract change, as `enums.py` does.
- [ ] …and the advisor models: `AdvisorStatus` (enabled, refusal reason, month spent and cap in
      cents, model), `ConversationCreate` (scope), `ConversationSummary`, `ConversationDetail`
      (turns with question, answer, figure checks, citations, limitations, status), `TurnCreate`
      (question, 1–2,000 characters), `Citation`, `FigureCheck`, and **`AdvisorEvent`** — a
      discriminated union of `turn_started`, `tool_call`, `text_delta`, `answer`, `regenerating`,
      `error`, `heartbeat`, `turn_complete`.
- [ ] Routes, all `501`: `GET /insights`; `GET /advisor/status`; `GET POST /advisor/conversations`;
      `GET DELETE /advisor/conversations/{conversation_id}`;
      `POST /advisor/conversations/{conversation_id}/turns` (declared `text/event-stream`);
      `GET /advisor/stream-check`.
- [ ] `AdvisorEvent` appears under `components` in `api-types.ts` although it is only ever sent as
      SSE. If `openapi-typescript` does not emit it from the route's `responses`, fix
      `scripts/export_openapi.py` — never hand-edit the generated file.
- [ ] ARCHITECTURE.md's endpoint table lists each new route against its implementing ticket; the
      inventory test enforces it.
- [ ] Money is `*_cents`, percentages `*_bps`, other ratios fixed-point with the scale in the name.
      A test walks every advisor schema and fails on a `float`.
- [ ] `make types` run and committed.
- [ ] Tests: contract test — each route exists and returns `501`, each schema name is in
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
