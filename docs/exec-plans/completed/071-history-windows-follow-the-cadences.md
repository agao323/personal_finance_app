# 071 — History windows follow the cadences
Status: done
Wave: 7   Lane: —
Blocked by: none
Read first: docs/PRODUCT.md

## Goal
"What you have used" is windowed by the calendar periods the credits themselves run on —
this month, this quarter, this half year, this year, all time — instead of 3 and 12 months
back, and it totals by cadence so a monthly credit's record is legible next to an annual one.

## Acceptance criteria
- [ ] The window control offers This month, This quarter, This half year, This year, All
      time. "All time" stays the default: no silent cut-off.
- [ ] `calendarWindowStart(window, today)` in `types.ts` returns the ISO start of the
      calendar month, quarter, half or year containing `today`, and null for all time.
- [ ] A per-cadence breakdown of realised value under the total, from the rows already
      returned. Cadences with nothing in the window are omitted rather than shown as zero.
- [ ] The panel says what the window means: a credit is counted by the period it belongs to,
      not by the day it was spent, which is the only thing the data records.
- [ ] Tests: unit — `calendarWindowStart` for each window, including a date in the first
      month of a quarter and one in the last, and 31 December. Component — switching the
      window refetches with the right `from`; the breakdown sums to the total; a cadence with
      no rows is absent.

## Files
- `web/src/components/cards/history.tsx`
- `web/src/components/cards/types.ts`
- `web/src/components/cards/history.test.tsx`, `types.test.ts`

## Notes
No API change. `GET /cards/history` already takes `from` and `to`, and the window boundaries
are plain calendar arithmetic, not perk-period arithmetic — no risk of a second
implementation of `add_months`.

The filter is on `period_start`, so "this month" means periods that began this month. An
annual credit whose period began in January does not appear under "this month" even if that
is when you spent it, because nothing records when you spent it. Say so in the panel rather
than pretending to a precision the rows do not have.
