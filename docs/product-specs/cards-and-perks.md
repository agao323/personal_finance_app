# Cards and perks

Credit cards and their recurring credits — $15 a month for rides, $50 a quarter for hotels,
$200 a year for airline fees. The page answers two questions: **what can I still use, and
when does it expire?** and **is this card paying for itself?** Nothing here touches net
worth; an unused credit is not money you have.

## What you can do

**The list** (`/cards`) — one compact row per card: name, issuer, value available this
period, and a mark when something on it is running out. Beside it (or above it on a narrow
screen) an **"Available to use"** overview across every card.

- **Add a card**: name, issuer, optional annual fee. No account or subtype language — a card
  is an account underneath, and the screen never makes you learn that (067).

**Available to use** — every unused credit whose period ends within a horizon you choose
(30 / 90 / 180 days / everything; default 90, remembered across reloads), soonest first, each
naming its card. Urgent ones are marked with a glyph and colour, and the total at stake and
the urgent subtotal are stated plainly. Mark a credit used from here.

**One card** (`/cards/[id]`, a real URL — bookmarkable, back button works; below the
breakpoint the list and the detail are separate screens) opens with a summary panel: the
card's name, credit count, available value, annual fee ("Charged 1 March" beneath it when a
renewal date is set) and **realised this year**. The panel's header carries **rename** and
**delete**; the fee control sits in the fee figure.

- **Credits**, grouped by cadence, monthly first. Add, edit, delete, **retire** and
  un-retire a credit; retired credits stay visible, separately.
- A **period grid** per credit: one chip per period (`Jan 2026`, `Q1 2026`, `H1 2026`,
  `2026`), oldest first, the current one marked. **One tap marks a period used at full
  value**; tap again to unmark. A separate control records or corrects a **partial amount**
  for any shown period. "Show earlier" goes further back; one toggle opens or closes every
  grid on the card.
- **History** of what you used on this card, windowed by This month / quarter / half year /
  year / All time (default all), with the realised total and a per-cadence breakdown.
- **Delete the card** — after typing its name, from a dialog that counts what goes. Closing
  it is offered first. Deleting the open card returns you to `/cards`.

## Rules and edge cases

- **Which period a date is in is decided only by the API** (`services/perks.py`); so are
  urgency and the reset schedule. The browser never does period arithmetic
  ([card-perks-period-engine](../design-docs/card-perks-period-engine.md)).
- **A new credit defaults to calendar boundaries**: months from the 1st, quarters Jan / Apr /
  Jul / Oct, halves Jan / Jul, the calendar year. Choosing "a different date" (for a
  cardmember-year credit) reveals a date input, and the form shows the next reset dates live,
  from `GET /perks/schedule`, and states plainly when an anchor is not calendar-aligned.
- **The anchor sets phase, not a start date**: periods before it can be recorded. A credit
  whose anchor is in the future has no current period yet.
- **Urgency is fixed per cadence**: within 7 days for monthly, 14 quarterly, 21 semiannual, 30
  annual; always on the last day. Never colour alone.
- **Marking is idempotent** — pressing twice is not an error; marking again with an amount
  updates it. `NULL` amount means full value; zero is refused.
- **Optimistic**: chips and marks flip immediately and revert visibly on failure. A change
  anywhere refreshes everything on the screen that could have changed, **in place** — no
  skeleton flash, no layout shift, open forms stay open.
- **Deleting a credit that has any recorded use is refused (409)**, and the screen offers
  retire instead, in the API's own words. Delete is for a credit added by mistake.
- **Editing a cadence or anchor keeps recorded history on the periods it was recorded
  against**, and the form warns that it will.
- **Realised this year** sums recorded amounts (face value when none was given) over
  redemptions whose period began in the calendar year — the same rule as the history panel.
  It never counts what is merely available. It is shown whenever there is any use, fee or no
  fee.
- **A card with no fee shows no fee**; clearing a fee sets it to null, not zero. The app
  reports the fee and the realised value and says nothing about whether to cancel.
- History windows count a credit **by the period it belongs to**, not the day it was spent —
  the only thing the data records — and the panel says so. Cadences with nothing in the
  window are omitted, not shown as zero.

## Endpoints

| Method | Path | Notes |
|---|---|---|
| GET | `/cards` | Cards with their credits, current period, used state, available value, fee, realised this year |
| POST | `/cards/{account_id}/perks` | Add a credit (credit-card accounts only; not closed) |
| PATCH DELETE | `/perks/{perk_id}` | Edit, retire (`is_active`); delete is 409 when it has history |
| POST DELETE | `/perks/{perk_id}/redemptions` | Mark or unmark the period containing `on` (default today), optional `amount_cents` |
| GET | `/perks/upcoming?within_days=` | Unused credits ending within the horizon, soonest first, with `is_urgent` and totals |
| GET | `/perks/{perk_id}/periods?back=&on=` | Recent periods with used state, for the grid |
| GET | `/perks/{perk_id}/history`, `/cards/history?account_id=&from=&to=` | Recorded uses, newest first, no default cut-off |
| GET | `/perks/schedule?cadence=&anchor_on=&on=` | Current period start, next resets, calendar-aligned or not |
| POST, PATCH, DELETE | `/accounts…` | A card is an account: create, rename, fee, delete — see [accounts-and-stakes](accounts-and-stakes.md) |

## Screens and code

`web/src/app/(dashboard)/cards/` (`layout.tsx` holds the list so it does not re-mount,
`page.tsx`, `[id]/page.tsx`) — `components/cards/*` (`card-list`, `card-detail`, `upcoming`,
`period-grid`, `perk-form`, `fee-form`, `history`, `remove-card`, `add-card`, `mark-button`,
`types.ts`). API: `services/perks.py`, `routers/cards.py` (which also holds query and
realised-value logic — TD-001), `models/card_perk.py`.

## Built by

049 (schema and period engine), 050 (API), 051 (first screen), 053–054 (partial use, fees,
urgency, editing, history), 055–059 (the rebuild: shell, upcoming panel, add/edit/delete,
history and backfill, net value), 061–064 (refresh bug, fee editing, removing a card, icons
and colour), 065 (review fixes; no plan file), 066–067 (master–detail, cards as cards),
068–069 (the period grid), 070 (refresh without flashing), 071 (history windows by cadence),
072 (controls on the card), 073 (the calendar year replaces the fee year), 074 (even chips),
076 (the anchor sets phase), 077 (partial amounts for any period), 078 (collapse every grid),
079 (calendar boundaries by default).
