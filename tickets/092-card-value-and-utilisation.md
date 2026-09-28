# 092 — Card value: what each card returned against its fee, and what went unused
Status: done
Wave: 9   Lane: S
Touches: none
Blocked by: 082, 087
Read first: docs/ADVISOR.md#analyses, tickets/059-net-card-value.md, tickets/073-the-calendar-year-replaces-the-fee-year.md

## Goal
"Is this card worth its fee?" is answered for each card and calendar year: fee, value realised,
value that was available, how much of it was used, and what the card netted.

## Acceptance criteria
- [x] `services/analysis/cards_value.py`, per card for a calendar year up to `today`: annual fee;
      realised value (`services/cards`' realised-value rule — the recorded amount, or face value for
      a one-tap mark, **never** what was merely available); available value (periods begun in the
      year × the perk's value); utilisation in bps; missed periods; net = realised − fee.
- [x] Containment on `period_start`, the rule ticket 073 settled, so this agrees with the Cards
      screen's "realised this year" figure by construction.
- [x] Tool `cards_value(year)`.
- [x] Tests: a card with no fee; a card whose fee exceeds realised value; a partial redemption; a
      retired perk; and a test that this module's realised figure equals `services/cards`' for the
      same card and year.

## Files
- `api/app/services/analysis/cards_value.py` (new)
- `api/app/advisor/tools/analysis.py`
- `api/tests/test_analysis_cards_value.py`

## Done — 2026-09-27

- **No fee recorded is unknown, not free** — the model schema already says so (`accounts.annual_fee`)
  and the tool says it again in the field description. Net value is then just the realised value.
- Available value counts only **active** perks, and only periods that began in the year on or
  after the perk's anchor, so a cardmember-year credit anchored in March 2025 contributes the
  period that began on 1 March 2026 to 2026, and not the one that began in 2025.
- Cards closed before the year began are left out; one closed during it is still reported.
