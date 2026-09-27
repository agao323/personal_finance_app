# 069 — Record use by period, not by date
Status: todo
Wave: 7   Lane: —
Blocked by: 068
Read first: docs/PRODUCT.md

## Goal
Recording a credit you already used becomes a grid of periods you toggle — months for a
monthly credit, quarters for a quarterly one, halves, years — instead of a date field with
two paragraphs explaining which period a date falls in.

## Acceptance criteria
- [ ] `BackfillForm` is replaced by `PeriodGrid`, which reads `/perks/{id}/periods` and
      renders one toggle per period, oldest first, newest last. The current period is in the
      grid and marked as current.
- [ ] A toggle marks or unmarks that period by posting the period's own start date, and is
      optimistic: the chip flips immediately and reverts visibly on failure.
- [ ] `periodLabel(cadence, start)` in `types.ts` gives the short label — `Jan 2026`,
      `Q1 2026`, `H1 2026`, `2026` — and every chip carries the exact half-open range in its
      accessible name, because a perk anchored mid-month has periods that are not calendar
      months.
- [ ] A period recorded with a partial amount shows that amount on the chip.
- [ ] "Show earlier" asks for more periods, and is absent once the perk's whole history is on
      screen.
- [ ] No date input anywhere in the cards screen, and no copy explaining how a date maps to
      a period.
- [ ] Tests: unit — `periodLabel` for all four cadences, including a period that is not
      calendar-aligned. Component — the grid renders a chip per period with used state from
      the API; clicking an unused chip posts that period's start; clicking a used one deletes
      it; a failed toggle restores the chip and says so.

## Files
- `web/src/components/cards/period-grid.tsx` (new)
- `web/src/components/cards/history.tsx` (drop `BackfillForm`)
- `web/src/components/cards/card-detail.tsx`
- `web/src/components/cards/types.ts`
- `web/src/components/cards/period-grid.test.tsx`, `types.test.ts`

## Notes
The data model already worked this way: a redemption is `(perk_id, period_start)` and its
presence is the whole state. Nothing stores the day you spent it. The date field was an input
detail leaking the period arithmetic into the interface, and removing it changes no rows.

Marking still goes through `POST /perks/{id}/redemptions` with `on` set to the period's start
date, which always resolves to that period. No new write endpoint.
