# 093 — The findings engine, and `GET /insights`
Status: todo
Wave: 9   Lane: S
Touches: none (implements a route declared in 081)
Blocked by: 081, 087, 088, 089, 090, 091, 092 (all in this lane — findings call services, not lane T's tools)
Read first: docs/ADVISOR.md#findings, docs/adr/0011-findings-are-computed-and-figures-are-grounded.md

## Goal
The analyses become ranked, structured findings — what needs attention, how urgently, on what
evidence, and where in the app to act — served by `GET /insights` and available to the advisor as
`get_findings`. Recommendations become testable with no model involved.

## Acceptance criteria
- [ ] `services/findings.py` implements every Wave 9 kind in ADVISOR.md#findings, with thresholds as
      one table of constants at the top of the module.
- [ ] Each finding: stable id (kind + subject ids + period), severity, a title rendered from a
      template and its evidence, evidence with source and as-of, an action from the `Screen` enum
      or none, and `impact_cents` where meaningful.
- [ ] Ranking: severity, then `impact_cents` descending, then kind order.
- [ ] **Stale evidence demotes**: severity capped at `notice` and the action becomes "update this
      balance" — except for `stale_balance` itself.
- [ ] `runway_low` states its three-month threshold as a default in its evidence, until goals exist.
- [ ] `GET /insights?scope=` implemented; spend-based findings are identical in both scopes.
- [ ] Works under `DEMO_MODE` — a read, no model.
- [ ] Tool `get_findings(scope, kinds?)`.
- [ ] Tests: unit — each kind at and either side of its threshold; ranking; the stale-demotion rule
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
