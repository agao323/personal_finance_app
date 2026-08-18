# 018 — Synthetic data generator
Status: done
Wave: 2   Lane: B
Blocked by: 012
Read first: docs/SECURITY.md#demo-isolation

## Goal
A seeded generator producing a coherent fake financial picture. Unblocks Lane C entirely and
is the demo deployment's only data source.

## Acceptance criteria
- [x] `api/scripts/seed_synthetic.py` generating users, institutions, accounts, ownership stakes, 24+ months of snapshots, categorised transactions, and a starter rule set
- [x] Seeded RNG — the same seed produces the same dataset
- [x] Coherent: correlated income and spend, realistic category mix, plausible growth curves
- [x] Deliberate edge cases: a 50%-owned rental property, a maxed 401k, a **mid-history ownership stake change**, a liability paying down, a **closed account**, matched **transfer pairs**, and some uncategorised transactions
- [x] Two users seeded so the Mine / Household toggle has something to show
- [x] **Refuses to run** against a database whose `data_marker` row says the data is real
- [x] `make seed` runs it against the local dev database
- [x] Tests: unit asserting the same seed reproduces an identical dataset; functional asserting the marker guard rejects a real-marked database

## Files
- `api/scripts/seed_synthetic.py`
- `api/tests/test_seed.py`
- `Makefile`

## Notes
**Ships first in this lane.** It is what lets Lane C work against real data instead of hand-
written mocks, and it is the demo's entire data source.

The edge cases exist to exercise the ownership math visibly rather than only in unit tests. A
50%-owned rental with a stake change partway through its history is the scenario most likely
to expose a bug in `net_worth()` — and it exposes it on screen, where it's obvious, instead of
in an aggregate that's merely slightly wrong.
