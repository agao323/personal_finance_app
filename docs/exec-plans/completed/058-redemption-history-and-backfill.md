# 058 — History, and adding a credit you used months ago
Status: done
Wave: 7   Lane: W4
Blocked by: 054
Read first: docs/exec-plans/completed/054-card-perks-api-for-editing-history-and-urgency.md

## Goal
Everything you have ever marked, and a way to record something you forgot to mark at the
time.

## Acceptance criteria
- [x] A history view from `GET /cards/history` — **first redemption to most recent, with
      no default cut-off**, plus an optional window
- [x] Each entry: date period, card, perk, amount realised (face value when the amount is
      `NULL`), and any note
- [x] Totals for the visible range: realised value, and how many periods went unused in
      that range. The second number is the one that changes behaviour
- [x] **Backfill** — record a redemption for a past period by naming a date inside it.
      `POST /perks/{id}/redemptions` already takes `on`; this is the first UI for it.
      Show which period the chosen date resolves to **before** saving, because "2 March"
      meaning the February period of a month-end anchor is genuinely surprising
- [x] Editing a past redemption's amount or note, and removing one
- [x] Refuses a date before the perk's first period, surfacing the API's 422
- [x] Tests: history renders and orders; the window filters; a backfill resolves to the
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

## Done — 2026-09-26

**All time is the default**, and a test asserts the first request carries no `from`
parameter. A silent window would hide exactly the old entries the request was about.

`missed_periods` is shown next to the realised total because it is the number that changes
behaviour — what you realised is reassuring, what you let expire is actionable.

A face-value entry is labelled "full", keeping "used it all" distinct from "used exactly
this much". Both are real states and collapsing them would lose the distinction that
partial amounts exist to capture.

Backfill sends the date and lets the service decide the period, rather than computing it in
the browser. A preview that disagreed with what got saved would be worse than none — and
the surprising case is real: "2 March" lands in the February period of a month-end anchor.
