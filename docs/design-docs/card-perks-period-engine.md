# Card perks: the period engine

A card perk is a recurring credit — $15 a month for rides, $50 a quarter for hotels, $200
a year for airline fees. The one question the app has to answer correctly is: **for a
given date, which period is this perk in, and has it been used?** Getting it wrong tells
you a credit is available when it is spent, which is exactly the class of wrong number
this project exists to avoid.

Code: `api/app/services/perks.py` — **the one place that decides what period a date is
in.** Routes and screens ask it rather than working periods out from a cadence
themselves, for the same reason rounding lives only in `services/ownership.py`.
User-facing behaviour: [product-specs/cards-and-perks.md](../product-specs/cards-and-perks.md).

## `card_perks` + `perk_redemptions`

A perk hangs off an `accounts` row with `subtype = 'credit_card'` — not a separate cards
table, which would be a second list of the same cards ([data-model.md](data-model.md#accounts)).
It stores a name, `value` (money), `cadence` (`monthly | quarterly | semiannual | annual`,
a Postgres enum shipped complete because a fifth value is a migration), `anchor_on`, and
`is_active` — retiring a perk keeps its history.

A redemption is one row per period used, **unique on `(perk_id, period_start)`** — a period
is used or it is not. `amount` is nullable: `NULL` means "used, full face value", which is
what a one-tap mark records; a value means partial; zero is refused
(`ck_perk_redemptions_amount_positive`), because an unused period already has a
representation — no row. Writing the face value into every redemption instead would freeze
a number the perk can legitimately change later (ticket 053).

**`period_start` is stored on the redemption, not recomputed at read time.** It is the fact
being recorded, and recomputing it from a cadence edited since would silently move history
— the mistake effective-dated ownership exists to prevent. History reads stored
`period_start` (ticket 054); editing a perk's cadence or anchor leaves recorded periods
where they were, and the form says so.

**Nothing here touches net worth.** A perk is not an asset and an unused credit is not money
you have. The model docstring says so, so nobody wires it into `services/net_worth.py`.

## The anchor sets phase

Perks reset on two clocks: calendar (1 January) and cardmember year (the anniversary of
opening the card). Rather than an enum plus an `opened_at` column on the most load-bearing
table in the schema, every perk carries **`anchor_on`, a date on which one of its periods
begins**. Periods are that date stepped by the cadence, so a calendar-year credit and one
that resets on the anniversary are the same arithmetic (ticket 049).

What `anchor_on` means has been corrected twice, and the current meaning is the one to
build on:

- **It is not a start date** (ticket 076). It says where boundaries fall — it is what makes
  a monthly credit reset on the 13th rather than the 1st — not when the credit came into
  existence. People entered the day they set the credit up in this app, and treating that
  as the beginning of history refused to record uses there was no reason to doubt. Periods
  before the anchor (negative indices) are legitimate; `period_containing` always answers.
  Whether a credit has *started* is a separate question: a perk whose anchor is in the
  future reports no current period, decided by comparing the anchor to the date.
  `missed_periods` still counts only from the anchor — a period before it can be recorded,
  but calling it missed would invent a failure.
- **It defaults to calendar-aligned** (ticket 079). 1 January aligns every cadence: months
  from the 1st, quarters at Jan/Apr/Jul/Oct, halves at Jan/Jul, and the year.
  `is_calendar_aligned` is the one definition (day 1, and `(month − 1) % months == 0`). A
  different anchor is right for a cardmember-year credit and wrong by accident the rest of
  the time, so the form requires choosing it and states it plainly. `GET /perks/schedule`
  previews the next reset dates **from the API** — never from arithmetic in the browser.

## The arithmetic

- **Half-open windows**, `[start, end)`, for the same reason ownership stakes are: with an
  inclusive end, a date on a boundary belongs to two periods.
- **Step from the anchor, never from the previous period.** `add_months` clamps to month
  end, so a perk anchored on the 31st gets 28 Feb then 31 Mar. Stepping from each previous
  result would give 28 Feb then 28 Mar and stay wrong for ever after one short month.
- `period_at(index)` and `period_containing(date)` are inverses and must agree; tests
  round-trip them across a month-end anchor and a February.
- **Nothing reads the clock.** Every function takes the date to evaluate, because the cases
  worth testing are all specific days — the rollover, 29 February, the 31st in a 30-day
  month. Routes take the date as a parameter defaulting to today.

## Urgency

`URGENT_WITHIN`: monthly 7 days, quarterly 14, semiannual 21, annual 30. **Fixed per
cadence, deliberately not configurable** — 30 days is noise on a monthly credit and too late
on an annual one, where a month is barely time to book the flight it pays for.
`is_urgent(cadence, days_remaining)` is `days_remaining <= URGENT_WITHIN[cadence]`, and
`days_remaining` is 0 on the last day. The browser reads `is_urgent` off the API and never
recomputes it.

## Realised value

"Realised this year" sums redemption amounts (face value when `NULL`) over redemptions whose
`period_start` falls in the **calendar year**, using the same helper as the history panel so
the two cannot disagree (ticket 073, which replaced the earlier fee-year window). It never
sums what is *available*, which would flatter every card. `fee_renews_on` now only tells you
when the fee is charged. The app reports the fee and the realised value side by side and
says nothing about whether to cancel — that judgement is the reader's.

## Tested by

`api/tests/test_perks.py` (hand-computed windows per cadence, month-end anchors, leap day,
boundary dates, negative indices, urgency at every boundary, calendar alignment for every
month), `test_cards.py` (marking, idempotent re-marking, partial amounts, 409 on deleting a
used perk, history windows, the schedule endpoint), and the web tests under
`web/src/components/cards/` (the grid, labels, urgency styling following the API flag).
