# 058 — History, and adding a credit you used months ago
Status: todo
Wave: 7   Lane: W4
Blocked by: 054
Read first: tickets/054-card-perks-api-for-editing-history-and-urgency.md

## Goal
Everything you have ever marked, and a way to record something you forgot to mark at the
time.

## Acceptance criteria
- [ ] A history view from `GET /cards/history` — **first redemption to most recent, with
      no default cut-off**, plus an optional window
- [ ] Each entry: date period, card, perk, amount realised (face value when the amount is
      `NULL`), and any note
- [ ] Totals for the visible range: realised value, and how many periods went unused in
      that range. The second number is the one that changes behaviour
- [ ] **Backfill** — record a redemption for a past period by naming a date inside it.
      `POST /perks/{id}/redemptions` already takes `on`; this is the first UI for it.
      Show which period the chosen date resolves to **before** saving, because "2 March"
      meaning the February period of a month-end anchor is genuinely surprising
- [ ] Editing a past redemption's amount or note, and removing one
- [ ] Refuses a date before the perk's first period, surfacing the API's 422
- [ ] Tests: history renders and orders; the window filters; a backfill resolves to the
      expected period and calls the API with that date; the pre-save period preview is
      correct for a month-end anchor

## Files
- `web/src/components/cards/history.tsx`
- `web/src/components/cards/history.test.tsx`

## Notes

The period preview is the part to get right. The engine in `services/perks.py` decides
which period a date lands in, so the preview must come from the API rather than a second
implementation in the browser — a preview that disagrees with what gets saved is worse
than no preview.
