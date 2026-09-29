# 086 — Card tools: cards, upcoming perks, perk history
Status: done
Wave: 9   Lane: T
Touches: none
Blocked by: 082, 083
Read first: docs/ADVISOR.md#tool-catalog, docs/ARCHITECTURE.md#card_perks--perk_redemptions

## Goal
The advisor can answer "which credits am I about to lose" and "what have I used this year" from
the same card services the Cards screen uses.

## Acceptance criteria
- [x] `cards_list`: cards, perks, current periods with days remaining and urgency, unused value,
      annual fee and renewal date, realised this calendar year. Card and perk names as `name_text`.
- [x] `cards_upcoming_perks(within_days 0–366)`: unused perks whose period ends in the window,
      soonest first, urgent flagged by `perks.is_urgent`.
- [x] `cards_perk_history(account_id?, perk_id?, start?, end?)`: realised total, missed periods, at
      most 50 redemptions with `note_text`. Span ≤ 3 years. Rows count against the turn budget.
- [x] All three pass `today` from the context as `on`; none reads the clock.
- [x] No scope parameter: perks are not net worth (`models/card_perk.py` says so), and nothing here
      is ownership-adjusted.
- [x] Tests: against `services/cards` on fixtures with a partial redemption, a missed period, a
      retired perk, and a perk urgent on its last day; a redemption note carrying a planted
      injection string comes back sanitised.

## Files
- `api/app/advisor/tools/cards.py` (new)
- `api/tests/test_advisor_tools_cards.py`

## Done — 2026-09-27

- **Period ends are the last usable day.** The period engine's `end` is the first day of the
  *next* period (half-open, as `services/perks.py` explains). The upcoming list and the history
  report `period_ends` as the last day you can still use a credit, because "ends 1 July" read by a
  person on 30 June means one more day than there is. `cards_list` keeps the engine's `end` and
  says in its field description which it is.
- A history window defaults to 1 January of the end year, and a call returns at most 50
  redemptions, newest first, with `showing_latest_only` when there were more.
- `NoArgs` moved into the framework for every tool without arguments.
