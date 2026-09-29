# 016 — Runway and burn rate endpoint
Status: done
Wave: 2   Lane: A
Blocked by: 015
Read first: docs/PRODUCT.md#burn-and-runway

## Goal
Gross burn rate and months of runway from liquid assets — the most actionable number in the
app right now.

## Acceptance criteria
- [x] `GET /runway` returning trailing 3/6/12-month average burn, ownership-adjusted liquid total, and months remaining
- [x] **Burn is gross spend excluding transfers. Income is not netted.**
- [x] Liquid total is ownership-adjusted and uses only `kind='liquid_asset'`
- [x] Excludes one-off outliers, with the outlier rule documented in the docstring and configurable
- [x] The **partial current month is excluded from the average** and reported separately, not averaged in
- [x] Months with no transaction data at all are excluded rather than counted as zero burn
- [x] Tests: unit for the outlier rule and the partial-month exclusion; functional asserting a partial current month does not depress the reported burn

## Files
- `api/app/routers/runway.py`
- `api/app/services/runway.py`
- `api/tests/test_runway.py`

## Notes
The partial-current-month case matters: naively averaging it in makes burn look artificially
low every single month, which is exactly the wrong direction for this number to be wrong in.

Gross rather than net is settled — see PRODUCT.md#burn-and-runway. This tile answers "how long
if income stopped."
