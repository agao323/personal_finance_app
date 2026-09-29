# Runway

How many months the household could live on its liquid assets if income stopped — the most
actionable number in the app.

## What you can do

- See **months of runway** and the **trailing gross burn** on the dashboard tile, for the
  trailing 3, 6 and 12 months.
- Switch Mine / Household; the liquid total follows the toggle.

## Rules and edge cases

- **Burn is gross spend, excluding transfers. Income is not netted.** Runway answers "how
  long if income stopped" — the only version worth a tile while income is coming in
  ([PRODUCT.md](../PRODUCT.md#burn-and-runway)). The tile says "gross", because a runway whose
  definition is ambiguous is worse than none.
- **Liquid assets are ownership-adjusted** and count only `kind = liquid_asset`. **Burn is not**
  split by ownership.
- **The partial current month is excluded** from the average, and the response says so
  (`partial_month_excluded`).
  Averaging it in makes burn look low every month — the wrong direction to be wrong in.
- **Months with no transaction data are excluded**, not counted as zero burn.
- **Outlier months are excluded**: a month spending more than 3× the window's median
  (`DEFAULT_OUTLIER_MULTIPLE`, configurable in the service) is left out. The service counts
  the months it excluded; the API does not expose that count.
- The average burn is rounded half-up to cents; `months_of_runway` is the one float in the
  contract, a display ratio never multiplied by a balance.

## Endpoints

| Method | Path | Notes |
|---|---|---|
| GET | `/runway?view=mine\|household` | Liquid total; per 3/6/12-month window, average monthly spend and months of runway (null when there is nothing to divide by); whether the partial month was excluded |

## Screens and code

`web/src/app/(dashboard)/page.tsx` — `components/tiles/runway.tsx`. API:
`services/runway.py` (uses `services/spend.py` and `services/ownership.py`), `routers/runway.py`.

## Built by

016 (the endpoint), 026 (the tile).
