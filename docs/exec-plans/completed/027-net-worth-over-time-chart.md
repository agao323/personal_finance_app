# 027 — Net worth over time chart
Status: done
Wave: 2   Lane: C
Blocked by: 026
Integrates with: 014
Read first: docs/ARCHITECTURE.md#data-model

## Goal
The primary chart: ownership-adjusted net worth over time, with range selection and an
assets/liabilities split view.

## Acceptance criteria
- [x] Line or area chart over `GET /net-worth/series`
- [x] Range selector: 3M, 6M, 1Y, YTD, All
- [x] Toggle between total and assets/liabilities split
- [x] Respects the Mine / Household toggle from 026
- [x] Accessible tooltip with formatted values and dates; keyboard navigable
- [x] Handles sparse, empty, and single-point history without breaking layout
- [x] Renders correctly in light and dark mode
- [x] Tests: component tests for range switching, empty series, single-point series, and tooltip content

## Files
- `web/src/components/charts/net-worth-chart.tsx`
- `web/src/components/charts/range-selector.tsx`
- `web/src/components/charts/net-worth-chart.test.tsx`

## Notes
Built against MSW mocks typed from `api-types.ts` — it does **not** wait for the
backend tickets above. Point it at the real endpoints once they land; ticket 038 verifies
the join.

Read the `dataviz` skill first — chart colours, axis treatment, tooltip behaviour, and dark
mode handling are covered there, and this is the chart the whole app is judged on.

The single-point case is not hypothetical: it's what the chart shows on day one, before the
sheet history import runs. It should look deliberate, not broken.
