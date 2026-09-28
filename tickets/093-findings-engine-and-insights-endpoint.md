# 093 — The findings engine, and `GET /insights`
Status: done
Wave: 9   Lane: S
Touches: none (implements a route declared in 081)
Blocked by: 081, 087, 088, 089, 090, 091, 092 (all in this lane — findings call services, not lane T's tools)
Read first: docs/ADVISOR.md#findings, docs/adr/0011-findings-are-computed-and-figures-are-grounded.md

## Goal
The analyses become ranked, structured findings — what needs attention, how urgently, on what
evidence, and where in the app to act — served by `GET /insights` and available to the advisor as
`findings_list`. Recommendations become testable with no model involved.

## Acceptance criteria
- [x] `services/findings.py` implements every Wave 9 kind in ADVISOR.md#findings, with thresholds as
      one table of constants at the top of the module.
- [x] Each finding: stable id (kind + subject ids + period), severity, a title rendered from a
      template and its evidence, evidence with source and as-of, an action from the `Screen` enum
      or none, and `impact_cents` where meaningful.
- [x] Ranking: severity, then `impact_cents` descending, then kind order.
- [x] **Stale evidence demotes**: severity capped at `notice` and the action becomes "update this
      balance" — except for `stale_balance` itself.
- [x] `runway_low` states its three-month threshold as a default in its evidence, until goals exist.
- [x] `GET /insights?scope=` implemented; spend-based findings are identical in both scopes.
- [x] Works under `DEMO_MODE` — a read, no model.
- [x] Tool `findings_list(scope, kinds?)`.
- [x] Tests: unit — each kind at and either side of its threshold; ranking; the stale-demotion rule
      and its exception; ids stable across two runs. Functional — `/insights` against the synthetic
      seed returns the expected kinds in order in both scopes.

## Files
- `api/app/services/findings.py` (new)
- `api/app/routers/insights.py`
- `api/app/advisor/tools/analysis.py`
- `api/tests/test_findings.py`
- `api/tests/test_api_insights.py`

## Notes
Titles are server text built from data, and a merchant name inside one is untrusted. The web
renders titles as text; that is 094's criterion and worth restating there.

The findings engine never calls a model and never will. When the advisor is on, the model explains
and prioritises findings for the question asked. It does not create them.

## Done — 2026-09-27

- **Findings are built straight into the contract's `Finding`**, cents and basis points, rather
  than into a dataclass mapped twice. They are a display read model with no other consumer, and a
  second shape would only be another place for them to drift.
- **Spikes come from one set of month totals.** `spend_trends.category_spikes` applies `monthly`'s
  rule to every leaf category from seven month queries, instead of seven queries per category.
- **Titles format money for reading only.** The advisor's tool renders titles as `title_text` —
  sanitised, because a merchant name can be in one — and a model quotes the evidence, which
  carries figure references, never the title.
- `GET /insights` evaluates today, as every other dashboard read does, and takes no `as_of`: the
  contract froze in 081 without one, and the engine is tested directly with named dates. The
  functional test over the seed asserts what holds on any day — ranking, shape, and identical
  spend findings in both views.
- A card fee renewing in exactly 60 days is reported and 61 is not; a runway of exactly 3.0 months
  is not low; a 5% net worth drop is not reported and 6% is.
