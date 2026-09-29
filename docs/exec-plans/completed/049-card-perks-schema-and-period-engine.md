# 049 — Card perks: schema and the period engine
Status: done
Wave: 6   Lane: —
Blocked by: none
Read first: docs/ARCHITECTURE.md#accounts

## Goal
Store the perks a credit card carries, and answer one question correctly: **for a given
date, which period is this perk in, and has it been used yet?**

No API and no screen in this ticket. The period arithmetic is the part that can be
subtly wrong for months without anyone noticing, so it lands on its own with tests.

## Why perks hang off `accounts`

`AccountSubtype.CREDIT_CARD` already exists. A separate `credit_cards` table would be a
second list of the same cards, and the two would disagree the first time one was renamed
or closed — the same reason `users` is the auth allowlist rather than one list beside
another.

Constrained to `subtype = 'credit_card'` so a perk cannot be attached to a mortgage.

## The one real design decision: an anchor date, not an anchor *type*

Card perks reset on two different clocks. Some are calendar — a $200 airline credit that
resets 1 January. Others run on the **cardmember year**, resetting on the anniversary of
opening the account. Getting this wrong tells you a perk is available when it is spent,
which is precisely the class of wrong number this project exists to avoid.

The obvious modelling is an enum — `calendar` or `anniversary` — plus a lookup of the
card's open date. `accounts` has `closed_at` but **no `opened_at`**, so that would mean a
migration on the most load-bearing table in the schema to support one feature.

Instead: every perk carries `anchor_on`, the date its **first period started**. Periods
are that date stepped by the cadence. One mechanism covers both clocks:

| Perk | Cadence | `anchor_on` | Periods |
|---|---|---|---|
| $200 airline credit, calendar | annual | 2026-01-01 | Jan 1 → Dec 31 |
| Annual credit on the cardmember year | annual | 2023-07-14 | Jul 14 → Jul 13 |
| $15 monthly credit | monthly | 2026-01-01 | the 1st of each month |
| $50 quarterly hotel credit | quarterly | 2026-01-01 | Jan/Apr/Jul/Oct |

No enum, no join, no `opened_at`. The anniversary *is* the anchor date.

## Acceptance criteria
- [x] `card_perks`: account, name, optional description, `value` money, `cadence`, and
      `anchor_on`. Perks can be retired without deleting their redemption history
- [x] `perk_redemptions`: perk, `period_start`, when it was marked, optional note.
      **Unique on (perk, period_start)** — a period is used or it is not
- [x] Cadence is a Postgres enum shipped complete: `monthly`, `quarterly`,
      `semiannual`, `annual` — the four the request named, and adding a fifth later is a
      migration, so ship the set now
- [x] `services/perks.py` computes the half-open window `[start, end)` containing a given
      date, from cadence and anchor. Half-open for the same reason ownership stakes are:
      an inclusive end date makes "which period is 1 January in" ambiguous
- [x] **Month-end anchors are handled explicitly.** A monthly perk anchored 31 January
      has no 31st in February. Clamp to the last day of the month, and step from the
      anchor rather than from the previous period, or 31 Jan → 28 Feb → 28 Mar drifts
      permanently after one short month
- [x] A date **before** the anchor is not in any period, and says so rather than
      returning a negative-index window
- [x] `value` is `Decimal` / `NUMERIC(19,2)`. Never float, per CLAUDE.md
- [x] **Nothing here touches net worth.** A perk is not an asset and an unused credit is
      not money you have. Stated in the model docstring so nobody wires it into
      `services/net_worth.py` later
- [x] Tests: hand-computed windows for each cadence; a month-end anchor across a short
      month and back out again; a leap day; a date on the exact boundary going to the
      later period; a date before the anchor; and the unique constraint refusing a second
      redemption for one period

## Files
- `api/app/models/card_perk.py`
- `api/app/models/enums.py`
- `api/alembic/versions/0005_card_perks.py`
- `api/app/services/perks.py`
- `api/tests/test_perks.py`

## Notes

**Redemption is binary**, because that is what was asked for: mark it used or not. A
partial redemption — $50 of a $200 credit — is a real thing and deliberately not modelled
here; add a ticket if it turns out to matter. Storing the perk's `value` is enough to
total what is unused.

**`period_start` is stored on the redemption rather than computed at read time.** It is
the fact being recorded — "this period was used" — and recomputing it later from a
cadence that had since been edited would silently move history, which is the mistake
effective-dated ownership exists to prevent.

## Done — 2026-08-26

**The anchor-date design held up under the tests, which is the point of writing them
first.** `test_a_cardmember_year_is_the_same_arithmetic` is the one that matters: a card
opened 14 July 2023 is, on 1 January 2026, still inside the period that began 14 July
2025. A calendar reading would report a fresh credit. No enum, no join, no `opened_at`
on `accounts` — the anniversary is the anchor.

**Stepping from the anchor rather than from the previous period** is the whole of the
month-end handling, and it is asserted directly: 31 January monthly gives 28 February
and then **31 March**, not 28 March. Stepping from each previous result would clamp once
and stay clamped for ever, and the drift would look plausible on every screen.

**One real bug, caught by the migration round trip.** The first version created the
`perk_cadence` type explicitly *and* declared it on the column, so `create_table` emitted
a second `CREATE TYPE` and the upgrade failed with "type already exists". 0001 declares
its six enums inline and drops them by name at the end of `downgrade`; 0005 now does the
same. Worth noting that the pure-function tests were all green while this was broken —
only the tests that touch a real migrated database found it, which is exactly why the
repo forbids `metadata.create_all()`.

`days_remaining` returns 0 on the last day of a period. Asserted on its own because
off-by-one there is the difference between "expires today" and "already gone", and that
number is going straight onto a screen.

465 passed.
