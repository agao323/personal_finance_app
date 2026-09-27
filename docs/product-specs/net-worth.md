# Net worth

The number the app exists for: what the household is worth, counting only the share each
person owns, now and on every past date.

## What you can do

- See **current net worth** on the dashboard, with assets and liabilities subtotals and the
  change against the prior month, absolute and as a percentage.
- Switch **Mine / Household**. Mine counts your stakes; Household counts every stake the
  household holds. The choice persists across navigation. This toggle is the entire
  multi-user surface of the app.
- See **net worth over time** as a chart, with ranges 3M, 6M, 1Y, YTD and All, and a toggle
  between the total and an assets / liabilities split. Tooltips are keyboard-navigable and
  show formatted values and dates.

## Rules and edge cases

- **Every figure is ownership-adjusted**, rounded half-up per account and then summed, so the
  total equals the rows ([ownership-and-rounding](../design-docs/ownership-and-rounding.md)).
- **A past date uses that date's balances and that date's stakes.** Changing a stake never
  rewrites the chart.
- Liabilities are stored positive and subtracted.
- An account with **no snapshot on or before a date is excluded**, not counted as zero.
- An account **closed** on or before a date is excluded from that date on.
- A balance carried forward **more than 90 days** still counts, and is reported as stale
  (`stale_account_ids`) — the dashboard prompts for an update. The series reports a stale
  count per point, but the chart does not draw it yet (TD-010).
- Household is always ≥ Mine; they are equal until a partner holds a stake.
- Empty history, a single point (day one, before the sheet import) and sparse history all
  render deliberately rather than as a broken chart.
- Card credits never count — an unused credit is not money you have.

## Endpoints

| Method | Path | Notes |
|---|---|---|
| GET | `/net-worth?as_of=&view=mine\|household` | Total, assets, liabilities, breakdown by kind, `stale_account_ids`. `as_of` defaults to today |
| GET | `/net-worth/series?from=&to=&interval=day\|week\|month&view=` | One point per interval, each with `stale_account_count` |

## Screens and code

`web/src/app/(dashboard)/page.tsx` — `components/tiles/net-worth.tsx`,
`components/charts/net-worth-chart.tsx`, `charts/range-selector.tsx`, `view-toggle.tsx`.
API: `services/net_worth.py`, `services/ownership.py`, `routers/net_worth.py`.

## Built by

013 (the calculation), 014 (endpoints), 026 (tiles and toggle), 027 (the chart), 040 (a seed
where the toggle reads sensibly), 052 (the series in a fixed number of queries).
