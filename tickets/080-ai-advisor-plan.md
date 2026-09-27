# 080 — AI advisor: questions answered, trends explained, recommendations grounded
Status: planning
Wave: 9–13   Lane: —
Blocked by: none for Wave 9. The model half has gates — see below, and do not treat them as a formality
Read first: docs/ADVISOR.md, docs/SECURITY.md#ai-agent, docs/DECISIONS.md

## Goal
Ask anything about the household's money — net worth, accounts, transactions, spending, runway,
cards and credits — and get an answer that explains what changed and why, plus recommendations
against the household's goals and current portfolio. Every figure in an answer is computed by the
app's own services and checked before it is shown.

**This ticket is a plan, not an implementation.** It is one ticket because it is one decision;
it ships as tickets 081–119, grouped into Waves 9–13 in `tickets/README.md`. Nothing here is
built yet.

## Why this shape
[SECURITY.md#ai-agent](../docs/SECURITY.md#ai-agent) fixed the constraints before anyone designed
the feature: read-only parameterised tools, no model-generated SQL, no fetch tool, no write tools,
every call logged, aggregates over rows. Planning it showed the feature is really two:

- **The no-model half** — tools, deterministic analyses, a findings engine, an Insights panel.
  Ordinary read-only code. It ships first and is useful alone.
- **The model half** — the loop, the provider, the chat. This is what "ships last" was about, and
  it still does, switched off until its gates hold.

[DECISIONS.md, 2026-09-27](../docs/DECISIONS.md) has the reasoning; ADRs 0009–0014 have the choices
between viable options.

## The constraints that drive the design
**The model never does arithmetic, and that has to be enforced rather than asked for.** Analyses
compute; a findings engine decides what is worth saying; the model sees figures pre-formatted and
copies them; a grounding check rejects any figure no tool returned
([ADR 0011](../docs/adr/0011-findings-are-computed-and-figures-are-grounded.md)).

**Every string in the database is untrusted.** Merchants and memos arrive from bank exports today
and from SimpleFIN after 075. They are sanitised at the tool boundary, marked as data by field
name, and the design assumes some injection will get through — which is why there is nowhere for
it to send anything.

**The browser is an egress.** A markdown image in an answer is a request to an attacker's server
with data in the query string. Three layers stop it: the API strips it, the renderer cannot draw
it, and the CSP would block it.

**Money is spent per question.** Caps before every call, a kill switch that defaults off, and a
provider-side spend limit that no bug here can bypass.

## Phases
### Phase 0 — Decisions (this ticket)
ADRs 0009–0014, the SECURITY.md threat model, the DECISIONS.md entry, ADVISOR.md, and these
tickets. **Done when the owner has accepted or amended the open decisions below.**

### Phase 1 — Wave 9: tools, analyses, findings, Insights (081–094)
Contract first (081), then the read models the tools need move out of routers into services
(082), then the tool framework (083). Three lanes: tools (084–086), analyses and findings
(087–093), web (094). Spending analysis leads, as decided on 2026-09-27. No model, no egress.

### Phase 2 — Wave 10, lane L: loop, audit, caps, grounding, evals (095–103, 107)
The advisor tables (095), the model client and price table (096), the loop (097), grounding
(098), the streaming endpoints (099), eval fixtures in CI (101) and the live `make eval` (102),
privacy and operations hardening (103), and switching it on (107).

### Phase 3 — Wave 10, lane W: the chat (100, 104–106)
The BFF forwards cancellation and does not buffer (100); the `/advisor` screen (104); streaming,
citations, staleness and unverified figures, with no links or images (105); CSP and the demo's
recorded examples (106). Lane W starts as soon as 081 lands — it builds against MSW, exactly as
Lane C did in Wave 2.

### Phase 4 — Wave 11: goals and the planning profile (108–111)
Goals — spending limits, emergency fund, savings targets — and a planning profile with stated
assumptions; goal-aware findings, tools and evals.

### Phase 5 — Wave 12: debt, allocation, projections (112–118)
Liability terms, tax treatment, account-level allocation
([ADR 0013](../docs/adr/0013-allocation-is-recorded-per-account-not-per-holding.md)); debt strategy
and allocation analyses; projections to PRODUCT's FIRE bar and what-if tools.

### Phase 6 — Wave 13, optional: the monthly review (119)
User-initiated, in-app only. Email or push would be egress.

**The order of Phases 4 and 5 is provisional.** `note_limitation` records every question the
advisor could not answer and why; a month of real use ranks them, and that ranking beats this
document's guess.

## Open decisions
1. **Model provider.** Recommended: the Anthropic API, `claude-opus-5`, behind a provider-neutral
   seam. Self-hosted open-weight models were investigated on 2026-09-27 — Fly's GPUs are retired,
   a laptop-hosted model would be offline whenever the laptop sleeps and would have to join
   production's private network, and a rented GPU is another third party. Full record and revisit
   conditions in [ADR 0009](../docs/adr/0009-advisor-model-provider.md).
2. **Row-level transactions to the provider.** Recommended: bounded — 25 rows a call, 100 a turn,
   descriptions cut to 80 characters and sanitised. Aggregates stay the default.
3. **Model and effort.** Recommended: `claude-opus-5` at `medium` effort; let `make eval` test
   `low`, and Sonnet 5 or Opus 5.5 if cost bites.
4. **Refusal fallbacks.** Recommended: on (`fallbacks: "default"`).
5. **Whose conversations are visible.** Recommended: each person sees their own; the cap is
   household-wide.
6. **Proactive insights.** Recommended: the Insights panel always on, chat on demand, the monthly
   review only if Wave 13 is wanted.
7. **Finding thresholds.** Recommended: the constants in ADVISOR.md#findings, revisited after a
   month.
8. **Demo.** Recommended: recorded examples ([ADR 0014](../docs/adr/0014-the-demo-advisor-replays-recorded-answers.md)).

Decided by the owner on 2026-09-27: transcripts in Postgres for 30 days; a $20 monthly cap;
allocation and fund types, never tickers; spending analysis first; the advisor stays general —
specific analyses are what make particular answers exact, not a narrowing of what can be asked.

## Gates on the model half
Wave 9 has none beyond this plan. **`ADVISOR_ENABLED` stays false in production** until:

- ADR 0008's restore drill has run against production — there is no real data to advise on
  before it, and nothing should read real data before a restore is proven;
- 103 is done (Sentry local variables off, logs without arguments, demo key guard);
- a passing `make eval` is recorded in ADVISOR.md#eval-runs;
- the `pfa-prod` Console workspace exists with a spend limit;
- ADR 0009 is accepted.

024 and 075 are **not** gates. Their absence makes answers shallower and staler, and the tools say
so rather than the advisor waiting.

## Testing
Every ticket ships unit and functional tests, per `tickets/README.md#tests`. Beyond that: the
whole loop runs in CI against a scripted model; expected eval answers are computed by the same
services and checked for drift in CI; the live suite is `make eval`, on demand, printing its cost.
Fixtures are synthetic — the eval overlay refuses a database marked real.

## Cost of not doing it
The dashboard answers the questions it was designed for. The ones that come up between visits —
why did that move, what is this charge, which subscription went up, is this card still worth it —
are answered today by exporting to a spreadsheet, which is the habit this app exists to end. The
Insights panel alone answers several of them without a model; that is the first thing worth
shipping, and it costs nothing to run.
