# 086 — Card tools: cards, upcoming perks, perk history
Status: todo
Wave: 9   Lane: T
Touches: none
Blocked by: 082, 083
Read first: docs/ADVISOR.md#tool-catalog, docs/ARCHITECTURE.md#card_perks--perk_redemptions

## Goal
The advisor can answer "which credits am I about to lose" and "what have I used this year" from
the same card services the Cards screen uses.

## Acceptance criteria
- [ ] `cards_list`: cards, perks, current periods with days remaining and urgency, unused value,
      annual fee and renewal date, realised this calendar year. Card and perk names as `name_text`.
- [ ] `cards_upcoming_perks(within_days 0–366)`: unused perks whose period ends in the window,
      soonest first, urgent flagged by `perks.is_urgent`.
- [ ] `cards_perk_history(account_id?, perk_id?, start?, end?)`: realised total, missed periods, at
      most 50 redemptions with `note_text`. Span ≤ 3 years. Rows count against the turn budget.
- [ ] All three pass `today` from the context as `on`; none reads the clock.
- [ ] No scope parameter: perks are not net worth (`models/card_perk.py` says so), and nothing here
      is ownership-adjusted.
- [ ] Tests: against `services/cards` on fixtures with a partial redemption, a missed period, a
      retired perk, and a perk urgent on its last day; a redemption note carrying a planted
      injection string comes back sanitised.

## Files
- `api/app/advisor/tools/cards.py` (new)
- `api/tests/test_advisor_tools_cards.py`
