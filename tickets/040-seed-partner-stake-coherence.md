# 040 — Seed: give the partner a stake in what the mortgage is against
Status: done
Wave: 2   Lane: B
Blocked by: —
Read first: tickets/018-synthetic-data-generator.md

## Goal
Make the seeded stake structure read as a plausible household, so the Mine / Household toggle
demonstrates ownership adjustment instead of looking like a bug.

## The problem
The ownership math is correct — this is a data-realism defect, not a math defect. Verified
against the current seed:

| | Mine | Household | delta |
|---|---|---|---|
| Assets | $541,030.29 | $541,581.16 | **+$550.87** |
| Liabilities | $188,854.93 | $307,174.93 | **+$118,320.00** |
| Net worth | $352,175.36 | $234,406.23 | **−$117,769.13** |

Both deltas are exact: $550.87 is 40% of the $1,377.17 Checking balance, and $118,320.00 is
40% of the $295,800.00 Mortgage. `services/ownership.py` is doing precisely what it should.

The cause is the 2025-06-01 stake transition. It moves the partner into 40% of the **Mortgage**
and 40% of **Checking** — a $295,800 liability and a $1,377 asset — while the Rental property
that mortgage is presumably secured against stays 50% Owner / 50% nobody. So the partner
joins the household holding debt and essentially no corresponding asset, and Household net
worth lands $118k *below* Mine.

## Acceptance criteria
- [x] The partner's 2025-06-01 stake transition covers an asset proportionate to the mortgage
      share — either give them a stake in the Rental property, or move the mortgage onto a
      primary-residence account they part-own
- [x] Household net worth is **greater than** Mine at every point in the series, and a test
      asserts it (the invariant that makes the toggle legible)
- [x] The mid-history stake change is preserved — it is 018's edge case and must keep exercising
      the effective-dated path
- [x] The 50%-owned Rental property is preserved as a distinct case: an asset the household owns
      a fraction of, with the other half outside the household
- [x] Seed remains deterministic under its seed; `test_seed.py` reproducibility test still passes

## Files
- `api/scripts/seed_synthetic.py`
- `api/tests/test_seed.py`

## Notes
Found while demoing the local app after Lane B closed. Not folded into 018 (done, committed)
because the fix changes generated data that 037's demo deployment serves, so it deserves its
own reviewable commit.

Worth doing before **037 (demo deployment)** — that deployment has this dataset as its only
data source, and "Household" reading $118k worse than "Mine" is the first thing a visitor
toggles. Not urgent for 024: that ticket replaces this data with real history anyway.

## Done — 2026-08-18

Took the ticket's second option: a **Primary residence** account, shared with the
partner on the same date the mortgage is. The rental keeps its 50% household stake, so
the "part-owned by someone outside the household" case survives intact — it is the only
account where even the Household view shows less than the asset is worth.

| | Mine | Household |
|---|---|---|
| Net worth | $692,793.29 | $797,486.95 |

**One criterion was worded wrong and I corrected it.** I had written "household is
greater than Mine at every point", which cannot hold: before the partner's stake
begins they hold nothing and the two are equal. The invariant that actually matters is
`household >= mine` everywhere — household sums a superset of your stakes, so it can
never be smaller — with strict inequality after the partner joins. Both are now tested,
the first across the whole 30-month series rather than at today, because a stake change
part way through history is exactly the thing that holds now and not in March.

**Found while reseeding:** the API container image predates the `webauthn` dependency
added in 034, so it crashed on import until rebuilt. `make dev` rebuilds; a plain
`docker compose restart api` does not.
